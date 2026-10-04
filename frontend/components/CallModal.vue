<script setup>
import { computed, ref, watch, nextTick } from 'vue'
const props = defineProps({ state: Object, username: String })
const duration = computed(() => `${String(Math.floor(props.state.duration / 60)).padStart(2, '0')}:${String(props.state.duration % 60).padStart(2, '0')}`)
const status = computed(() => ({ outgoing_ringing: 'Calling…', incoming_ringing: 'Incoming call…', connecting: 'Connecting…', connected: 'Connected', declined: 'Call declined', busy: 'User is currently busy.', missed: 'No answer / Missed call', ended: 'Call ended', failed: 'Failed to connect' })[props.state.phase] || '')
const incomingVoice = computed(() => props.state.type === 'audio' && props.state.phase === 'incoming_ringing')
const callerInitials = computed(() => props.state.peer?.trim().split(/\s+/).slice(0, 2).map(part => part[0]?.toUpperCase()).join('') || '')
const incomingAnswer = ref(null)
const incomingDecline = ref(null)
let previousFocus
watch(incomingVoice, async visible => {
 if (visible) {
  previousFocus = document.activeElement
  await nextTick()
  if (incomingVoice.value) incomingAnswer.value?.focus()
 } else if (previousFocus?.isConnected) { previousFocus.focus(); previousFocus = null }
}, { immediate: true })
function cycleIncomingFocus(event) {
 if (event.target === incomingAnswer.value) incomingDecline.value?.focus()
 else incomingAnswer.value?.focus()
}
const defaultPanelOpen = () => !globalThis.matchMedia?.('(max-width: 720px)').matches
const panelOpen = ref(defaultPanelOpen())
const remoteVideo = ref(null)
const audioBlocked = ref(false)
async function playRemote() {
 const video = remoteVideo.value
 if (!video) return
 try { await video.play() } catch {
  audioBlocked.value = true
  video.muted = true
  video.play().catch(() => {})
 }
}
function enableAudio() {
 audioBlocked.value = false
 remoteVideo.value.muted = !props.state.speaker
 playRemote()
}
const localMain = ref(false)
const active = computed(() => ['outgoing_ringing', 'connecting', 'connected'].includes(props.state.phase))
const localVisible = computed(() => props.state.camera && !!props.state.localStream)
const remoteVisible = computed(() => props.state.phase === 'connected' && !!props.state.remoteStream)
const mainName = computed(() => localMain.value ? `${props.username} (You)` : props.state.peer)
const previewName = computed(() => localMain.value ? props.state.peer : `${props.username} (You)`)
watch(() => props.state.phase, phase => {
 if (phase === 'idle') { localMain.value = false; panelOpen.value = defaultPanelOpen(); audioBlocked.value = false }
})
</script>
<template>
 <div class="call-overlay" :class="{ 'video-overlay': state.type === 'video', 'incoming-voice-overlay': incomingVoice }" id="callOverlay" :style="{ display: state.phase === 'idle' ? 'none' : 'flex' }" role="dialog" aria-modal="true" aria-label="Call">
  <section v-if="incomingVoice" class="iv-card" aria-labelledby="incomingVoiceName" @keydown.tab.prevent="cycleIncomingFocus">
   <div class="iv-glow" aria-hidden="true"></div>
   <div class="iv-type" role="status"><i aria-hidden="true"></i>Incoming voice call</div>
   <div class="iv-avatar"><span>{{ callerInitials }}</span><i class="iv-wave" aria-hidden="true"></i><i class="iv-wave iv-wave-two" aria-hidden="true"></i></div>
   <h2 id="incomingVoiceName">{{ state.peer }}</h2>
   <p>is calling you...</p>
   <div class="iv-actions">
    <div class="iv-action-group"><button ref="incomingDecline" type="button" class="iv-action iv-decline" aria-label="Decline call" @click="state.decline()"><svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7.4 10.6a15.6 15.6 0 0 0 6 6l2-2a2 2 0 0 1 2.1-.5c1 .4 2.1.6 3.2.7a2 2 0 0 1 1.8 2v3a2 2 0 0 1-2.2 2A20 20 0 0 1 2.2 3.7 2 2 0 0 1 4.2 1.5h3a2 2 0 0 1 2 1.8c.1 1.1.4 2.2.7 3.2a2 2 0 0 1-.5 2.1Z"/></svg></button><span>Decline</span></div>
    <div class="iv-action-group"><button ref="incomingAnswer" type="button" class="iv-action iv-answer" aria-label="Answer call" @click="state.answer()"><svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7.4 10.6a15.6 15.6 0 0 0 6 6l2-2a2 2 0 0 1 2.1-.5c1 .4 2.1.6 3.2.7a2 2 0 0 1 1.8 2v3a2 2 0 0 1-2.2 2A20 20 0 0 1 2.2 3.7 2 2 0 0 1 4.2 1.5h3a2 2 0 0 1 2 1.8c.1 1.1.4 2.2.7 3.2a2 2 0 0 1-.5 2.1Z"/></svg></button><span>Answer</span></div>
   </div>
  </section>
  <div class="audio-call-interface" id="audioCallInterface" v-show="state.type !== 'video' && !incomingVoice">
   <div class="call-avatar" id="callAvatar">{{ state.peer?.[0]?.toUpperCase() }}</div>
   <div class="call-user-name" id="callUserName">{{ state.peer }}</div>
   <div class="call-status" id="callStatus" role="status">{{ status }}</div>
   <div class="call-duration" id="callDuration">{{ duration }}</div>
   <div v-if="state.phase === 'incoming_ringing'" class="incoming-call-controls">
    <button class="call-control-btn accept" id="acceptCallBtn" @click="state.answer()"><i class="fas fa-phone"></i> Answer</button>
    <button class="call-control-btn decline" id="declineCallBtn" @click="state.decline()"><i class="fas fa-phone-slash"></i> Decline</button>
   </div>
   <div v-else-if="['outgoing_ringing', 'connecting', 'connected'].includes(state.phase)" class="call-controls">
    <button class="call-control-btn mute" id="muteBtn" :aria-pressed="state.muted" title="Mute microphone" @click="state.mute()"><i :class="state.muted ? 'fas fa-microphone-slash' : 'fas fa-microphone'"></i></button>
    <button class="call-control-btn speaker" id="speakerBtn" :aria-pressed="!state.speaker" title="Toggle speaker" @click="state.toggleSpeaker()"><i :class="state.speaker ? 'fas fa-volume-up' : 'fas fa-volume-mute'"></i></button>
    <button class="call-control-btn hangup" id="hangupBtn" :title="state.phase === 'outgoing_ringing' ? 'Cancel Call' : 'End Call'" @click="state.hangup()"><i class="fas fa-phone"></i></button>
   </div>
  </div>
  <section v-if="state.type === 'video'" class="vc-view" id="videoCallInterface" aria-label="Video call">
   <header class="vc-header">
    <div class="vc-heading"><h2>Video call</h2><p role="status"><span class="vc-dot" :class="{ connected: state.phase === 'connected' }"></span>{{ state.phase === 'incoming_ringing' ? 'Incoming video call' : status }}<span v-if="state.phase === 'connected'"> · 2 participants · {{ duration }}</span></p></div>
    <button v-if="audioBlocked && state.speaker" class="vc-audio-unlock" @click="enableAudio">Enable call audio</button>
    <button class="vc-panel-toggle" :aria-expanded="panelOpen" aria-controls="videoParticipants" @click="panelOpen = !panelOpen"><i class="fas fa-users"></i><span>Participants</span></button>
   </header>
   <div class="vc-content" :class="{ 'panel-closed': !panelOpen }">
    <div class="vc-stage">
     <div class="vc-main">
      <video ref="remoteVideo" v-show="remoteVisible" autoplay playsinline @loadedmetadata="playRemote" :muted="!state.speaker || audioBlocked" :srcObject="state.remoteStream" :class="{ 'vc-hidden': localMain }" aria-label="Remote camera"></video>
      <video v-if="localMain && localVisible" autoplay muted playsinline :srcObject="state.localStream" class="vc-local" aria-label="Your camera"></video>
      <div v-if="localMain ? !localVisible : !remoteVisible" class="vc-placeholder"><div>{{ mainName?.[0]?.toUpperCase() }}</div><p>{{ mainName }}</p><p>{{ localMain ? (state.camera ? 'Camera unavailable' : 'Camera off') : status }}</p></div>
      <div class="vc-shade"></div><span class="vc-name">{{ mainName }}<i v-if="localMain && state.muted" class="fas fa-microphone-slash"></i></span>
     </div>
     <button class="vc-preview" :aria-label="`Show ${previewName} on main stage`" @click="localMain = !localMain">
      <video v-if="localMain ? remoteVisible : localVisible" autoplay playsinline muted :srcObject="localMain ? state.remoteStream : state.localStream" :class="{ 'vc-local': !localMain }"></video>
      <div v-else class="vc-placeholder"><div>{{ previewName?.[0]?.toUpperCase() }}</div></div>
      <div class="vc-shade"></div><span class="vc-preview-name">{{ previewName }}</span><span class="vc-switch">Tap to switch</span>
     </button>
    </div>
    <aside v-show="panelOpen" class="vc-panel" id="videoParticipants">
     <div class="vc-panel-heading"><div><h3>Participants</h3><p>{{ state.phase === 'connected' ? '2 in this call' : status }}</p></div><button aria-label="Close participants" @click="panelOpen = false">×</button></div>
     <button class="vc-person" @click="localMain = false"><span class="vc-avatar">{{ state.peer?.[0]?.toUpperCase() }}</span><span>{{ state.peer }}<small>{{ status }}</small></span></button>
     <button class="vc-person" @click="localMain = true"><span class="vc-avatar">{{ username?.[0]?.toUpperCase() }}</span><span>{{ username }} (You)<small>{{ state.muted ? 'Microphone muted' : 'Microphone on' }} · {{ state.camera ? 'Camera on' : 'Camera off' }}</small></span></button>
    </aside>
   </div>
   <footer class="vc-toolbar">
    <div class="vc-room">Video call<small>{{ state.peer }}</small></div>
    <div class="vc-controls" v-if="state.phase === 'incoming_ringing'">
     <div class="vc-control"><button class="vc-answer" aria-label="Answer video call" @click="state.answer()"><i class="fas fa-phone"></i></button><span>Answer</span></div>
     <div class="vc-control"><button class="vc-end" aria-label="Decline video call" @click="state.decline()"><i class="fas fa-phone-slash"></i></button><span>Decline</span></div>
    </div>
    <div class="vc-controls" v-else-if="active">
     <div class="vc-control"><button id="videoMuteBtn" :class="{ off: state.muted }" :aria-pressed="state.muted" :aria-label="state.muted ? 'Unmute microphone' : 'Mute microphone'" @click="state.mute()"><i :class="state.muted ? 'fas fa-microphone-slash' : 'fas fa-microphone'"></i></button><span>{{ state.muted ? 'Unmute' : 'Mute' }}</span></div>
     <div class="vc-control"><button id="videoCamBtn" :class="{ off: !state.camera }" :aria-pressed="!state.camera" :aria-label="state.camera ? 'Turn camera off' : 'Turn camera on'" @click="state.toggleCamera()"><i :class="state.camera ? 'fas fa-video' : 'fas fa-video-slash'"></i></button><span>Camera</span></div>
     <div class="vc-control"><button :class="{ off: !state.speaker }" :aria-pressed="!state.speaker" :aria-label="state.speaker ? 'Mute speaker' : 'Enable speaker'" @click="state.toggleSpeaker()"><i :class="state.speaker ? 'fas fa-volume-up' : 'fas fa-volume-mute'"></i></button><span>Speaker</span></div>
     <div class="vc-control"><button id="videoHangupBtn" class="vc-end" :aria-label="state.phase === 'outgoing_ringing' ? 'Cancel call' : 'End call'" @click="state.hangup()"><i class="fas fa-phone-slash"></i></button><span>{{ state.phase === 'outgoing_ringing' ? 'Cancel' : 'End call' }}</span></div>
    </div>
    <p v-else class="vc-terminal" role="status">{{ status }}</p>
   </footer>
  </section>

  <audio v-if="state.type === 'audio'" autoplay :muted="!state.speaker" :srcObject="state.remoteStream"></audio>
 </div>
</template>

<style scoped>
.incoming-voice-overlay { background:rgba(9,14,24,.76); backdrop-filter:blur(3px); padding:16px; overflow-y:auto; }
.iv-card { position:relative; box-sizing:border-box; flex-shrink:0; width:min(100%,440px); min-height:535px; overflow:hidden; padding:35px 34px 28px; border:1px solid #ffffff3d; border-radius:28px; background:linear-gradient(145deg,#5a83ee 0%,#765fd4 54%,#9b55bd 100%); color:white; text-align:center; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; box-shadow:0 35px 85px #0509126b; }
.iv-card:before { position:absolute; inset:0; background:radial-gradient(circle at 16% 2%,#ffffff33,transparent 32%),radial-gradient(circle at 90% 95%,#ffffff1c,transparent 35%); content:''; pointer-events:none; }
.iv-glow { position:absolute; top:-100px; left:50%; width:300px; height:300px; transform:translateX(-50%); border-radius:50%; background:#ffffff1f; filter:blur(65px); pointer-events:none; }
.iv-type { position:relative; display:inline-flex; align-items:center; gap:8px; padding:7px 11px; border:1px solid #ffffff26; border-radius:999px; background:#ffffff1a; color:#ffffffd6; font-size:10px; font-weight:650; letter-spacing:.3px; text-transform:uppercase; }
.iv-type i { width:7px; height:7px; border-radius:50%; background:#77f2ae; animation:iv-pulse 1.4s ease-in-out infinite; box-shadow:0 0 0 4px #77f2ae24; }
.iv-avatar { position:relative; width:124px; height:124px; margin:38px auto 25px; }
.iv-avatar > span { position:relative; z-index:2; display:grid; box-sizing:border-box; width:100%; height:100%; place-items:center; border:3px solid #ffffff85; border-radius:50%; background:#ffffff21; font-size:41px; font-weight:680; box-shadow:inset 0 0 40px #ffffff14; backdrop-filter:blur(12px); }
.iv-wave { position:absolute; inset:-14px; border:1px solid #ffffff6b; border-radius:50%; animation:iv-wave 2s ease-out infinite; }
.iv-wave-two { animation-delay:.85s; }
.iv-card h2 { position:relative; margin:0; font-size:27px; letter-spacing:-.5px; overflow-wrap:anywhere; }
.iv-card > p { position:relative; min-height:21px; margin:7px 0 0; color:#ffffffc7; font-size:14px; }
.iv-actions { position:relative; display:flex; align-items:center; justify-content:center; gap:65px; margin-top:47px; }
.iv-action-group { display:flex; flex-direction:column; align-items:center; gap:10px; color:#ffffffc7; font-size:10px; font-weight:600; }
.iv-action { display:grid; width:64px; height:64px; place-items:center; padding:0; border:0; border-radius:21px; color:white; cursor:pointer; transition:transform 160ms ease,box-shadow 160ms ease; }
.iv-action:hover { transform:translateY(-3px); }
.iv-action:focus-visible { outline:3px solid white; outline-offset:5px; }
.iv-decline { background:#ed3f55; box-shadow:0 11px 25px #6914284d; }
.iv-decline svg { transform:rotate(135deg); }
.iv-answer { background:#2fc47b; box-shadow:0 11px 25px #0f59394d; }
@keyframes iv-pulse { 0%,100% { opacity:1; } 50% { opacity:.35; } }
@keyframes iv-wave { 0% { opacity:.7; transform:scale(.84); } 100% { opacity:0; transform:scale(1.35); } }
@media(max-width:700px) { .iv-card { min-height:510px; padding-inline:22px; border-radius:25px; } .iv-avatar { width:112px; height:112px; } .iv-action { width:59px; height:59px; border-radius:19px; } }
@media(max-height:570px) { .incoming-voice-overlay { align-items:flex-start!important; } }
@media(prefers-reduced-motion:reduce) { .iv-type i,.iv-wave { animation:none; } .iv-action { transition:none; } }

.video-overlay { background: #f8f9fc; }
.vc-view { width:100%; height:100dvh; display:grid; grid-template-rows:86px minmax(0,1fr) 104px; background:#f8f9fc; color:#222b3b; text-align:left; }
.vc-view * { box-sizing:border-box; }
.vc-view button { font:inherit; cursor:pointer; border:0; }
.vc-view button:focus-visible { outline:3px solid #78a8ff; outline-offset:3px; }
.vc-header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 28px; border-bottom:1px solid #e5e8ee; background:#fff; }
.vc-heading h2 { margin:0; font-size:20px; letter-spacing:-.4px; }
.vc-heading p { display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin:5px 0 0; color:#747d8e; font-size:12px; }
.vc-dot { width:7px; height:7px; border-radius:50%; background:#9ba5b6; }
.vc-dot.connected { background:#26b56e; box-shadow:0 0 0 3px #dff7eb; }
.vc-audio-unlock { background:#edf3ff; color:#2568d8; border-radius:12px; padding:10px; font-size:12px!important; }
.vc-panel-toggle { display:flex; align-items:center; gap:8px; height:40px; padding:0 13px; border-radius:12px; background:#2f77ed; color:white; font-size:12px!important; }
.vc-content { display:grid; min-height:0; grid-template-columns:minmax(0,1fr) 330px; gap:18px; padding:20px 22px; }
.vc-content.panel-closed { grid-template-columns:minmax(0,1fr); }
.vc-stage { position:relative; display:grid; min-width:0; min-height:0; place-items:center; overflow:hidden; border-radius:22px; background:radial-gradient(circle at 50% 15%,#33415d,transparent 42%),#111723; }
.vc-stage:before { position:absolute; inset:0; background-image:radial-gradient(#ffffff12 1px,transparent 1px); background-size:22px 22px; content:''; pointer-events:none; }
.vc-main { position:relative; width:min(100% - 56px,1100px); height:min(100% - 50px,650px); overflow:hidden; border:1px solid #ffffff1f; border-radius:18px; background:#242b38; box-shadow:0 24px 70px #00000059; }
.vc-view video { width:100%; height:100%; object-fit:cover; display:block; }
.vc-main video { position:absolute; inset:0; }
.vc-local { transform:scaleX(-1); }
.vc-main .vc-hidden { visibility:hidden; }
.vc-placeholder { display:grid; width:100%; height:100%; place-content:center; text-align:center; color:#aeb7c8; }
.vc-placeholder div { display:grid; width:84px; height:84px; margin:0 auto 13px; place-items:center; border-radius:50%; background:linear-gradient(135deg,#4a84ef,#8b5dd7); color:white; font-size:30px; font-weight:700; }
.vc-placeholder p { margin:5px 0; font-size:13px; }
.vc-shade { position:absolute; inset:0; background:linear-gradient(180deg,transparent 55%,#05080e9e); pointer-events:none; }
.vc-name { position:absolute; bottom:18px; left:18px; display:flex; align-items:center; gap:8px; max-width:calc(100% - 36px); padding:9px 12px; border:1px solid #ffffff1f; border-radius:10px; background:#0e121bb8; color:white; font-size:12px; overflow-wrap:anywhere; backdrop-filter:blur(12px); }
.vc-preview { position:absolute; z-index:3; right:28px; bottom:28px; width:clamp(150px,20%,220px); aspect-ratio:16/10; padding:0; overflow:hidden; border:2px solid #ffffffd9!important; border-radius:15px; color:white; background:#252d3b; box-shadow:0 14px 36px #00000061; transition:transform 160ms ease; }
.vc-preview:hover { transform:translateY(-3px); border-color:#78a8ff!important; }
.vc-preview .vc-placeholder div { width:40px; height:40px; font-size:15px; margin:0; }
.vc-preview-name { position:absolute; bottom:9px; left:10px; right:10px; text-align:left; font-size:10px; font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.vc-switch { position:absolute; top:8px; right:8px; padding:4px 6px; border-radius:6px; background:#080c14a6; font-size:8px; opacity:0; }
.vc-preview:hover .vc-switch,.vc-preview:focus-visible .vc-switch { opacity:1; }
.vc-panel { min-width:0; padding:20px; overflow-y:auto; border:1px solid #e5e8ee; border-radius:18px; background:white; }
.vc-panel-heading { display:flex; justify-content:space-between; gap:8px; margin-bottom:22px; }
.vc-panel-heading h3 { margin:0; font-size:17px; letter-spacing:-.3px; }
.vc-panel-heading p { margin:4px 0 0; color:#828a98; font-size:11px; }
.vc-panel-heading button { width:34px; height:34px; border-radius:12px; background:transparent; color:#525d70; font-size:24px; }
.vc-person { display:flex; align-items:center; width:100%; gap:11px; margin-bottom:9px; padding:10px; border:1px solid #e9ecf1!important; border-radius:13px; background:#fafbfc; color:inherit; text-align:left; font-size:12px!important; }
.vc-person:hover { border-color:#b9cff5!important; background:#f4f7fd; }
.vc-person > span:last-child { min-width:0; overflow-wrap:anywhere; }
.vc-avatar { display:grid; place-items:center; flex:0 0 42px; height:42px; border-radius:12px; background:linear-gradient(135deg,#4a84ef,#8b5dd7); color:white; }
.vc-person small { display:block; margin-top:4px; color:#828a98; font-size:10px; }
.vc-toolbar { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; padding:0 28px; border-top:1px solid #e2e6ed; background:white; }
.vc-room { font-size:12px; font-weight:600; overflow-wrap:anywhere; }
.vc-room small { display:block; margin-top:5px; color:#828a98; font-size:10px; }
.vc-controls { display:flex; align-items:center; justify-content:center; gap:14px; }
.vc-control { display:flex; flex-direction:column; align-items:center; min-width:56px; gap:6px; color:#6f7887; font-size:9px; font-weight:600; }
.vc-control button { display:grid; place-items:center; width:48px; height:48px; border-radius:15px; background:#eef1f5; color:#293446; font-size:18px; transition:transform 160ms ease; }
.vc-control button:hover { transform:translateY(-2px); }
.vc-control button.off { background:#feecef; color:#d83e51; }
.vc-control button.vc-end { width:60px; background:#e93f4f; color:white; box-shadow:0 7px 18px #e93f4f40; }
.vc-control button.vc-answer { background:#26b56e; color:white; }
.vc-terminal { text-align:center; font-size:14px; }
@media(max-width:900px) { .vc-content { grid-template-columns:minmax(0,1fr) 270px; } .vc-main { width:calc(100% - 32px); height:calc(100% - 32px); } .vc-room { display:none; } .vc-toolbar { grid-template-columns:1fr; } }
@media(max-width:720px) { .vc-view { grid-template-rows:74px minmax(0,1fr) 88px; } .vc-header { padding:0 14px; } .vc-heading h2 { font-size:16px; } .vc-heading p { font-size:10px; } .vc-panel-toggle span { display:none; } .vc-content { display:block; padding:10px; } .vc-stage { height:100%; border-radius:16px; } .vc-main { width:calc(100% - 20px); height:calc(100% - 20px); } .vc-preview { right:18px; bottom:18px; width:125px; border-radius:12px; } .vc-switch { display:none; } .vc-panel { position:absolute; z-index:10; top:82px; right:12px; bottom:98px; width:min(330px,100% - 24px); box-shadow:0 24px 70px #00000026; } .vc-toolbar { padding:10px; } .vc-controls { gap:12px; } .vc-control { min-width:52px; } .vc-control button { width:46px; height:46px; border-radius:14px; } .vc-control button.vc-end { width:56px; } }
@media(prefers-reduced-motion:reduce) { .vc-view button { transition:none; } }
</style>
