import test from 'node:test'
import assert from 'node:assert/strict'
import { createCallController, newCallState } from '../frontend/runtime/calls.js'

function user(name) {
 const state = newCallState(), sent = [], peers = [], streams = []
 const ring = { starts: 0, stops: 0, start() { this.starts++ }, stop() { this.stops++ }, dispose() { this.stop() } }
 class Peer {
  connectionState = 'new'
  constructor() { peers.push(this) }
  addTrack() {}
  async createOffer() { return { type: 'offer', sdp: 'offer' } }
  async createAnswer() { return { type: 'answer', sdp: 'answer' } }
  async setLocalDescription(value) { this.localDescription = value }
  async setRemoteDescription(value) { this.remoteDescription = value }
  async addIceCandidate() {}
  close() { this.connectionState = 'closed'; this.onconnectionstatechange?.() }
  connect() { this.connectionState = 'connected'; this.onconnectionstatechange?.() }
 }
 const env = { crypto: { randomUUID: () => name + '-' + sent.length }, RTCPeerConnection: Peer,
  navigator: { mediaDevices: { async getUserMedia({ video }) {
   const tracks = [{ enabled: true, stopped: false, stop() { this.stopped = true } }]
   if (video) tracks.push({ enabled: true, stopped: false, stop() { this.stopped = true } })
   const stream = { getTracks: () => tracks, getAudioTracks: () => [tracks[0]], getVideoTracks: () => tracks.slice(1) }
   streams.push(stream); return stream
  } } } }
 const controller = createCallController({ state, username: name, send: msg => sent.push(msg), iceServers: [], env, ringer: ring })
 return { state, sent, peers, streams, ring, controller, env }
}

for (const type of ['audio', 'video']) {
 test(`${type}: waits for answer and actual connection, timer excludes ringing`, async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] })
  const a = user('alice'), b = user('bob')
  t.after(() => { a.controller.dispose(); b.controller.dispose() })
  await a.controller.start(type, 'bob')
  assert.equal(a.state.phase, 'outgoing_ringing'); assert.equal(a.state.duration, 0)
  await b.controller.handle(a.sent[0])
  assert.equal(b.state.phase, 'incoming_ringing'); assert.equal(b.streams.length, 0)
  assert.equal(a.ring.starts, 1); assert.equal(b.ring.starts, 1)
  a.peers[0].connect()
  assert.equal(a.state.phase, 'outgoing_ringing')
  t.mock.timers.tick(21000)
  await b.controller.answer()
  assert.equal(b.state.phase, 'connecting')
  await a.controller.handle(b.sent.find(msg => msg.type === 'call-accept'))
  assert.equal(a.state.phase, 'connecting'); assert.equal(a.state.duration, 0)
  const answer = b.sent.find(msg => msg.type === 'call-answer')
  await a.controller.handle(answer)
  assert.equal(a.state.phase, 'connected'); assert.equal(a.state.duration, 0)
  b.peers[0].connect()
  assert.equal(b.state.phase, 'connected'); assert.equal(b.state.duration, 0)
  t.mock.timers.tick(1000)
  assert.equal(a.state.duration, 1); assert.equal(b.state.duration, 1)
  assert.ok(a.ring.stops > 0 && b.ring.stops > 0)
  a.controller.hangup()
  await b.controller.handle(a.sent.at(-1))
  assert.equal(a.state.phase, 'ended'); assert.equal(b.state.phase, 'ended')
  assert.ok(a.streams[0].getTracks().every(track => track.stopped))
  assert.ok(b.streams[0].getTracks().every(track => track.stopped))
 })

 test(`${type}: decline and cancellation never connect`, async t => {
  const a = user('alice'), b = user('bob')
  t.after(() => { a.controller.dispose(); b.controller.dispose() })
  await a.controller.start(type, 'bob'); await b.controller.handle(a.sent[0])
  b.controller.decline(); await a.controller.handle(b.sent.at(-1))
  assert.equal(a.state.phase, 'declined'); assert.equal(b.state.phase, 'declined')
  assert.equal(a.state.duration, 0); assert.equal(b.streams.length, 0)
  await a.controller.start(type, 'bob'); await b.controller.handle(a.sent.at(-1))
  a.controller.hangup(); await b.controller.handle(a.sent.at(-1))
  assert.equal(a.sent.at(-1).type, 'call-cancel'); assert.equal(a.sent.at(-1).duration, 0)
  assert.equal(b.state.phase, 'missed')
 })

 test(`${type}: busy and stale answers cannot replace an active call`, async t => {
  const a = user('alice'), b = user('bob'), c = user('charlie')
  t.after(() => { a.controller.dispose(); b.controller.dispose(); c.controller.dispose() })
  await a.controller.start(type, 'bob'); await b.controller.handle(a.sent[0])
  await c.controller.start(type, 'bob'); await b.controller.handle(c.sent[0])
  await c.controller.handle(b.sent.at(-1))
  assert.equal(c.state.phase, 'busy'); assert.equal(b.state.phase, 'incoming_ringing')
  await a.controller.handle({ type: 'call-answer', callType: type, receiver: 'alice', sender: 'bob', callId: 'stale', sdp: {} })
  assert.equal(a.state.phase, 'outgoing_ringing')
 })

 test(`${type}: timeout stops ringing and reports no completed duration`, async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] })
  const a = user('alice'); t.after(() => a.controller.dispose())
  await a.controller.start(type, 'bob')
  t.mock.timers.tick(45000)
  assert.equal(a.state.phase, 'missed'); assert.equal(a.state.duration, 0)
  assert.equal(a.sent.at(-1).status, 'missed'); assert.ok(a.ring.stops > 0)
  t.mock.timers.tick(1500); assert.equal(a.state.phase, 'idle')
 })
}

test('permission denial and socket failure clean up without ringing', async t => {
 const a = user('alice'); t.after(() => a.controller.dispose())
 await a.controller.start('audio', 'bob')
 a.controller.fail()
 assert.equal(a.state.phase, 'failed'); assert.ok(a.ring.stops > 0)
 assert.ok(a.streams[0].getTracks().every(track => track.stopped))
 const b = user('bob'); t.after(() => b.controller.dispose())
 b.env.navigator.mediaDevices.getUserMedia = async () => { throw new Error('Permission denied') }
 await b.controller.start('video', 'alice')
 assert.equal(b.state.phase, 'failed'); assert.ok(b.ring.stops > 0)
})


test('video controls update actual media tracks without ending the call', async t => {
 const a = user('alice'), b = user('bob')
 t.after(() => { a.controller.dispose(); b.controller.dispose() })
 await a.controller.start('video', 'bob')
 await b.controller.handle(a.sent[0]); await b.controller.answer()
 await a.controller.handle(b.sent.find(msg => msg.type === 'call-accept'))
 await a.controller.handle(b.sent.find(msg => msg.type === 'call-answer'))
 a.peers[0].connect(); b.peers[0].connect()
 a.state.mute()
 assert.equal(a.streams[0].getAudioTracks()[0].enabled, false)
 a.state.toggleCamera()
 assert.equal(a.streams[0].getVideoTracks()[0].enabled, false)
 assert.equal(a.state.camera, false); assert.equal(a.state.phase, 'connected')
 a.state.mute(); a.state.toggleCamera(); a.state.toggleSpeaker()
 assert.equal(a.streams[0].getAudioTracks()[0].enabled, true)
 assert.equal(a.streams[0].getVideoTracks()[0].enabled, true)
 assert.equal(a.state.speaker, false); assert.equal(a.state.phase, 'connected')
})
