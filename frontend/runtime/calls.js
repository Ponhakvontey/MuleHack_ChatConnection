export const newCallState = () => ({ phase: 'idle', type: 'audio', peer: '', duration: 0, muted: false, speaker: true, camera: true, localStream: null, remoteStream: null })

// One ringtone engine shared by both directions. Browser autoplay restrictions
// can prevent sound on an untouched receiver tab; visual ringing still works.
export function createRinger() {
 let context, pulseTimer, oscillators = []
 const silence = () => { for (const oscillator of oscillators) { try { oscillator.stop() } catch {} }; oscillators = [] }
 const stop = () => { clearInterval(pulseTimer); pulseTimer = null; silence(); if (context) context.suspend().catch(() => {}) }
 return {
  start() {
   if (pulseTimer) return
   const AudioContext = globalThis.AudioContext || globalThis.webkitAudioContext
   if (!AudioContext) return
   context ||= new AudioContext()
   context.resume().catch(() => {})
   const pulse = () => {
    silence()
    const gain = context.createGain(); gain.gain.value = .06; gain.connect(context.destination)
    for (const frequency of [440, 480]) {
     const oscillator = context.createOscillator(); oscillator.frequency.value = frequency
     oscillator.connect(gain); oscillator.start(); oscillator.stop(context.currentTime + 1)
     oscillators.push(oscillator)
    }
   }
   pulse(); pulseTimer = setInterval(pulse, 3000)
  }, stop,
  dispose() { stop(); if (context) context.close().catch(() => {}) }
 }
}

export function createCallController({ state, username, send, iceServers, env = globalThis, ringer = createRinger(), onEnd = () => {} }) {
 let peer, stream, offer, candidates = [], callId, accepted = false, generation = 0
 let timeout, durationTimer, closeTimer, startedAt = 0, disposed = false
 const active = () => ['outgoing_ringing', 'incoming_ringing', 'connecting', 'connected'].includes(state.phase)
 const signal = (type, extra = {}) => {
  try { send({ type, callType: state.type, sender: username, receiver: state.peer, callId, ...extra }); return true }
  catch { return false }
 }
 function transition(phase) {
  state.phase = phase
  if (phase.endsWith('_ringing')) ringer.start(); else ringer.stop()
 }
 function cleanup() {
  generation++; clearTimeout(timeout); clearInterval(durationTimer)
  ringer.stop(); peer?.close(); peer = null
  stream?.getTracks().forEach(track => track.stop()); stream = null
  state.localStream = null; state.remoteStream = null; candidates = []; offer = null
 }
 function finish(phase = 'ended', notify = false) {
  if (!active()) return
  const wasRinging = state.phase.endsWith('_ringing')
  if (notify) signal(wasRinging ? 'call-cancel' : 'call-end', { status: phase === 'missed' || wasRinging ? 'missed' : phase === 'failed' ? 'failed' : 'ended', duration: startedAt ? Math.floor((Date.now() - startedAt)/1000) : 0 })
  if (notify && phase === 'ended' && startedAt) onEnd(state.type, Math.floor((Date.now() - startedAt)/1000))
  transition(phase); cleanup(); clearTimeout(closeTimer)
  closeTimer = setTimeout(() => { state.phase = 'idle' }, 1500)
 }
 function begin(phase, type, name, id) {
  clearTimeout(closeTimer); generation++
  callId = id; accepted = false; startedAt = 0; state.duration = 0
  state.type = type; state.peer = name; state.muted = false; state.speaker = true; state.camera = true
  transition(phase)
  timeout = setTimeout(() => finish('missed', phase === 'outgoing_ringing'), 45000)
 }
 function connecting() {
  transition('connecting'); clearTimeout(timeout)
  timeout = setTimeout(() => finish('failed', true), 20000)
 }
 function connected() {
  if (!accepted || state.phase !== 'connecting' || peer?.connectionState !== 'connected') return
  transition('connected'); clearTimeout(timeout); startedAt = Date.now(); state.duration = 0
  durationTimer = setInterval(() => { state.duration = Math.floor((Date.now() - startedAt)/1000) }, 1000)
 }
 async function media(token) {
  const acquired = await env.navigator.mediaDevices.getUserMedia({ audio: true, video: state.type === 'video' })
  if (disposed || token !== generation || !active()) { acquired.getTracks().forEach(track => track.stop()); return false }
  stream = acquired; state.localStream = acquired
  acquired.getAudioTracks().forEach(track => { track.enabled = !state.muted })
  return true
 }
 function setupPeer() {
  peer = new env.RTCPeerConnection({ iceServers })
  const currentPeer = peer, token = generation
  peer.onicecandidate = event => { if (token === generation && event.candidate && active()) signal('ice-candidate', { candidate: event.candidate }) }
  peer.ontrack = event => { if (token === generation && accepted) state.remoteStream = event.streams[0] }
  peer.onconnectionstatechange = () => {
   if (token !== generation || currentPeer !== peer || !active()) return
   if (peer.connectionState === 'connected') connected()
   else if (['failed', 'closed'].includes(peer.connectionState)) finish('failed', true)
   else if (peer.connectionState === 'disconnected') {
    clearTimeout(timeout); timeout = setTimeout(() => { if (peer?.connectionState === 'disconnected') finish('failed', true) }, 10000)
   }
  }
  stream.getTracks().forEach(track => peer.addTrack(track, stream))
 }
 async function flushCandidates() { for (const candidate of candidates) await peer.addIceCandidate(candidate); candidates = [] }
 async function start(type, receiver) {
  if (disposed || active() || !receiver) return
  begin('outgoing_ringing', type, receiver, env.crypto.randomUUID())
  const token = generation
  try {
   if (!await media(token)) return
   setupPeer(); const localPeer = peer
   const sdp = await localPeer.createOffer()
   if (token !== generation) return
   await localPeer.setLocalDescription(sdp)
   if (token !== generation) return
   if (!signal('call-offer', { sdp: localPeer.localDescription || sdp })) finish('failed')
  } catch { if (token === generation) finish('failed', true) }
 }
 async function answer() {
  if (state.phase !== 'incoming_ringing') return
  accepted = true; connecting(); const token = generation
  if (!signal('call-accept')) { finish('failed'); return }
  try {
   if (!await media(token)) return
   setupPeer(); const localPeer = peer
   await localPeer.setRemoteDescription(offer)
   if (token !== generation) return
   await flushCandidates()
   const sdp = await localPeer.createAnswer()
   if (token !== generation) return
   await localPeer.setLocalDescription(sdp)
   if (token !== generation) return
   if (!signal('call-answer', { sdp: localPeer.localDescription || sdp })) { finish('failed'); return }
   connected()
  } catch { if (token === generation) finish('failed', true) }
 }
 function decline() { if (state.phase === 'incoming_ringing') { signal('call-decline', { status: 'declined' }); finish('declined') } }
 async function handle(msg) {
  if (msg.receiver !== username || typeof msg.type !== 'string' || (!msg.type.startsWith('call-') && msg.type !== 'ice-candidate')) return false
  if (msg.type === 'call-offer') {
   if (!['audio', 'video'].includes(msg.callType) || !msg.sender || !msg.sdp) return true
   if (active()) {
    if (msg.callId !== callId) send({ type: 'call-busy', callType: msg.callType, sender: username, receiver: msg.sender, callId: msg.callId, status: 'busy' })
    return true
   }
   begin('incoming_ringing', msg.callType, msg.sender, msg.callId)
   offer = msg.sdp; return true
  }
  if (!active() || msg.sender !== state.peer || msg.callType !== state.type || (callId && msg.callId !== callId)) return true
  try {
   if (msg.type === 'call-accept' && state.phase === 'outgoing_ringing') {
    accepted = true; connecting()
   } else if (msg.type === 'call-answer' && ['outgoing_ringing', 'connecting'].includes(state.phase) && peer) {
    accepted = true
    if (state.phase !== 'connecting') connecting()
    const token = generation
    await peer.setRemoteDescription(msg.sdp)
    if (token !== generation) return true
    await flushCandidates(); connected()
   } else if (msg.type === 'ice-candidate' && msg.candidate) {
    if (!peer?.remoteDescription) candidates.push(msg.candidate)
    else await peer.addIceCandidate(msg.candidate)
   } else if (msg.type === 'call-decline') finish('declined')
   else if (msg.type === 'call-busy') finish('busy')
   else if (['call-end', 'call-cancel', 'call-missed'].includes(msg.type)) finish(msg.status === 'failed' ? 'failed' : msg.type === 'call-missed' || msg.status === 'missed' ? 'missed' : 'ended')
  } catch { finish('failed', true) }
  return true
 }
 const controller = {
  start, answer, decline, handle, hangup: () => finish('ended', true),
  mute() { state.muted = !state.muted; stream?.getAudioTracks().forEach(track => { track.enabled = !state.muted }) },
  speaker() { state.speaker = !state.speaker },
  camera() { state.camera = !state.camera; stream?.getVideoTracks().forEach(track => { track.enabled = state.camera }) },
  fail() { finish('failed', true) },
  dispose() { if (active()) finish('ended', true); disposed = true; clearTimeout(closeTimer); cleanup(); state.phase = 'idle'; ringer.dispose() }
 }
 Object.assign(state, { answer: controller.answer, decline: controller.decline, hangup: controller.hangup, mute: controller.mute, toggleSpeaker: controller.speaker, toggleCamera: controller.camera })
 return controller
}
