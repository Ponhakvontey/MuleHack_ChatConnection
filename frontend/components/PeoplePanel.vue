<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { backendFetch } from '../services/auth.js'
const props = defineProps({ blockedOnly: Boolean })
const emit = defineEmits(['conversations', 'message', 'changed'])
const state = ref({ friends: [], incoming: [], outgoing: [], recommended: [], blocked: [], conversations: [] })
const query = ref(''), results = ref([]), error = ref(''), loading = ref(false), busy = ref(false)
let timer, searchVersion = 0, disposed = false
async function read(path) {
 const response = await backendFetch(path)
 const data = await response.json()
 if (!response.ok) throw new Error(data.error || 'Unable to load people.')
 return data
}
async function refresh() {
 try {
  const data = await read('/api/social/state')
  if (disposed) return
  state.value = data; emit('conversations', data.conversations); emit('changed')
 } catch (failure) { if (!disposed) error.value = failure.message }
}
async function search() {
 const version = ++searchVersion
 loading.value = true; error.value = ''
 try {
  const data = await read('/api/social/search?q=' + encodeURIComponent(query.value))
  if (version === searchVersion && !disposed) results.value = data.users
 } catch (failure) { error.value = failure.message }
 finally { if (version === searchVersion) loading.value = false }
}
async function act(user, action) {
 if (busy.value) return
 busy.value = true; error.value = ''
 try {
  const response = await backendFetch('/api/social/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: user.id, action }) })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'Unable to update relationship.')
  await refresh()
  if (query.value) await search()
  if (action === 'message') emit('message', data.username)
 } catch (failure) { error.value = failure.message }
 finally { busy.value = false }
}
defineExpose({ refresh })
onMounted(() => { refresh(); timer = setInterval(refresh, 10000); window.addEventListener('talky:relationships-changed', refresh) })
onUnmounted(() => { disposed = true; clearInterval(timer); window.removeEventListener('talky:relationships-changed', refresh) })
</script>

<template>
 <div class="people-panel">
  <p v-if="error" role="alert">{{ error }}</p>
  <template v-if="blockedOnly">
   <h3>Blocked Users</h3>
   <p v-if="!state.blocked.length">No blocked users.</p>
   <div v-for="user in state.blocked" :key="user.id" class="person">
    <span>{{ user.full_name || user.username }}<small>@{{ user.username }}</small></span>
    <button class="profile-action-btn" :disabled="busy" @click="act(user, 'unblock')">Unblock</button>
   </div>
  </template>
  <template v-else>
   <form class="search-container" @submit.prevent="search">
    <input v-model="query" class="search-input" aria-label="Search people" placeholder="Search username or name...">
    <button class="profile-action-btn" :disabled="loading">Search</button>
   </form>
   <p v-if="loading" role="status">Searching…</p>
   <section v-for="group in [{ title: 'Search Results', users: results, show: !!query }, { title: 'Incoming Requests', users: state.incoming, show: true }, { title: 'Outgoing Requests', users: state.outgoing, show: true }, { title: 'Friends', users: state.friends, show: true }, { title: 'Recommended People', users: state.recommended, show: true }]" :key="group.title">
    <template v-if="group.show">
     <h3>{{ group.title }}</h3>
     <p v-if="!group.users.length">{{ group.title === 'Search Results' ? 'No people found.' : group.title === 'Friends' ? 'No friends yet.' : group.title === 'Recommended People' ? 'No recommendations yet.' : 'No requests.' }}</p>
     <div v-for="user in group.users" :key="user.id" class="person">
      <div class="user-avatar-initial">{{ user.username[0]?.toUpperCase() }}</div>
      <span>{{ user.full_name || user.username }}<small>@{{ user.username }}</small><small v-if="user.reason">{{ user.reason }}</small></span>
      <div class="person-actions">
       <button v-if="user.relationship === 'NONE'" class="profile-action-btn primary" :disabled="busy" @click="act(user, 'request')">Add Friend</button>
       <template v-else-if="user.relationship === 'PENDING_SENT'"><small>Request Sent</small><button class="profile-action-btn" :disabled="busy" @click="act(user, 'cancel')">Cancel Request</button></template>
       <template v-else-if="user.relationship === 'PENDING_RECEIVED'"><button class="profile-action-btn primary" :disabled="busy" @click="act(user, 'accept')">Accept</button><button class="profile-action-btn" :disabled="busy" @click="act(user, 'decline')">Decline</button></template>
       <button v-else-if="user.relationship === 'FRIENDS'" class="profile-action-btn primary" :disabled="busy" @click="act(user, 'message')">Message</button>
       <button class="profile-action-btn" :disabled="busy" @click="act(user, 'block')">Block</button>
      </div>
     </div>
    </template>
   </section>
  </template>
 </div>
</template>

<style scoped>
.people-panel { padding: 16px; }
.people-panel h3 { margin: 20px 0 12px; font-size: 16px; }
.people-panel p, small { color: var(--text-secondary); }
.person { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--border-color); }
.person > span { flex: 1; min-width: 100px; overflow-wrap: anywhere; }
.person small { display: block; font-size: 12px; margin-top: 3px; }
.person-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.search-container { display: flex; align-items: center; gap: 8px; }
.search-input { min-width: 0; }
.people-panel button { font-family: inherit; }
</style>
