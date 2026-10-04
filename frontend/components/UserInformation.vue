<script setup>
import { onMounted, reactive, ref } from 'vue'
import { authState, backendFetch } from '../services/auth.js'
defineProps({ error: String })
defineEmits(['sign-out'])
const fields = [
  ['full_name', 'Full Name', 120], ['display_name', 'Nickname', 80],
  ['phone', 'Phone Number', 40], ['organization', 'School / Organization', 160],
  ['major', 'Major / Department', 120], ['bio', 'Bio', 1000]
]
const profile = reactive(Object.fromEntries(fields.map(([key]) => [key, ''])))
const loading = ref(true), saving = ref(false), exists = ref(false)
const loaded = ref(false)
const editing = ref(false), verifyingEmail = ref(false), emailCode = ref('')
const changingPassword = ref(false)
const account = reactive({ username: '', email: '' })
const passwords = reactive({ current_password: '', new_password: '', confirm_password: '' })
let savedProfile = {}, savedAccount = {}
function snapshot() { savedProfile = { ...profile }; savedAccount = { ...account } }
function cancelEdit() { Object.assign(profile, savedProfile); Object.assign(account, savedAccount); editing.value = false; verifyingEmail.value = false; emailCode.value = ''; message.value = ''; profileError.value = '' }
async function request(path, body) {
  const response = await backendFetch('/api/user/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'Unable to save changes.')
  return data
}
async function verifyEmail() {
  saving.value = true; profileError.value = ''
  try { await request('verify-account-email', { code: emailCode.value }); verifyingEmail.value = false; await saveProfile(true) }
  catch (failure) { profileError.value = failure.message }
  finally { saving.value = false }
}
async function updatePassword() {
  saving.value = true; message.value = ''; profileError.value = ''
  try {
    if (passwords.new_password !== passwords.confirm_password) throw new Error('New passwords do not match.')
    const data = await request('change-password', passwords)
    for (const key in passwords) passwords[key] = ''
    changingPassword.value = false; message.value = data.message
  } catch (failure) { profileError.value = failure.message }
  finally { saving.value = false }
}
const message = ref(''), profileError = ref('')
async function loadProfile() {
  loading.value = true
  profileError.value = ''
  try {
    const response = await backendFetch('/api/user/profile')
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || 'Unable to load your information.')
    exists.value = data.profile !== null
    for (const [key] of fields) profile[key] = data.profile?.[key] || ''
    Object.assign(account, authState.user)
    snapshot()
    editing.value = !exists.value
    loaded.value = true
  } catch (failure) { profileError.value = failure.message }
  finally { loading.value = false }
}
async function saveProfile(verified = false) {
  if ((saving.value && verified !== true) || !loaded.value) return
  message.value = ''; profileError.value = ''
  if (fields.some(([key, , max]) => profile[key].length > max)) {
    profileError.value = 'Please shorten the fields to their allowed lengths.'
    return
  }
  saving.value = true
  try {
    const accountResult = await request('account', { ...account, profile: { ...profile } })
    if (accountResult.otp_required) { verifyingEmail.value = true; return }
    authState.user = accountResult.user
    Object.assign(profile, accountResult.profile)
    exists.value = true
    snapshot()
    editing.value = false
    message.value = 'Your information has been updated successfully.'
    if (accountResult.renamed) {
      authState.signingOut = true
      localStorage.removeItem('lastChatUser')
      sessionStorage.setItem('showUserInformation', 'true')
      window.location.reload()
    }
  } catch (failure) { profileError.value = failure.message }
  finally { saving.value = false }
}
onMounted(loadProfile)
</script>

<template>
  <div class="user-information">
    <p v-if="loading" role="status">Loading information…</p>
    <form v-else-if="loaded" class="profile-details" @submit.prevent="saveProfile()">
      <div class="profile-summary">
        <div>
          <strong v-if="savedProfile.full_name">{{ savedProfile.full_name }}</strong>
          <span>@{{ savedAccount.username }}</span>
        </div>
        <button v-if="!editing" class="edit-button" type="button" :disabled="saving" @click="editing = true; message = ''; profileError = ''">
          <i class="fas fa-pen" aria-hidden="true"></i>Edit Information
        </button>
      </div>
      <section class="form-section">
        <div class="section-heading">
          <div class="section-icon"><i class="fas fa-user" aria-hidden="true"></i></div>
          <div><h2>Account information</h2><p>Your account details</p></div>
        </div>
        <div class="form-grid">
          <label for="account-username">Username
            <input id="account-username" v-model="account.username" autocomplete="username" maxlength="50" required :disabled="!editing || saving || verifyingEmail">
          </label>
          <label for="account-email">Email address
            <input id="account-email" v-model="account.email" autocomplete="email" type="email" required :disabled="!editing || saving || verifyingEmail">
          </label>
        </div>
      </section>
      <section class="form-section">
        <div class="section-heading">
          <div class="section-icon"><i class="fas fa-pen" aria-hidden="true"></i></div>
          <div><h2>Personal information</h2><p>Help people know you better</p></div>
        </div>
        <div class="form-grid two-column">
          <label v-for="[key, label, max] in fields" :key="key" :for="'user-info-' + key" :class="{ 'full-field': !['full_name', 'display_name'].includes(key) }">
            {{ label }}
            <textarea v-if="key === 'bio'" :id="'user-info-' + key" v-model="profile[key]" :maxlength="max" rows="3" :disabled="!editing || saving || verifyingEmail" />
            <input v-else :id="'user-info-' + key" v-model="profile[key]" :type="key === 'phone' ? 'tel' : 'text'" :autocomplete="key === 'full_name' ? 'name' : key === 'phone' ? 'tel' : key === 'organization' ? 'organization' : undefined" :maxlength="max" :disabled="!editing || saving || verifyingEmail">
            <small v-if="key === 'bio' && editing">{{ profile.bio.length }}/{{ max }}</small>
          </label>
        </div>
      </section>
      <div v-if="editing" class="profile-actions">
        <button class="cancel-button" type="button" :disabled="saving" @click="cancelEdit">Cancel</button>
        <button v-if="!verifyingEmail" class="save-button" type="submit" :disabled="saving || authState.signingOut">
          {{ saving ? 'Saving…' : exists ? 'Save Changes' : 'Save Information' }}
        </button>
      </div>
    </form>
    <form v-if="verifyingEmail" class="form-section verification-form form-grid" @submit.prevent="verifyEmail">
      <label for="account-code">Verification code sent to your new email
        <input id="account-code" v-model="emailCode" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required :disabled="saving">
      </label>
      <button class="save-button" :disabled="saving">Verify and Save Changes</button>
    </form>
    <section class="security-section">
      <div class="security-copy">
        <div class="section-icon"><i class="fas fa-lock" aria-hidden="true"></i></div>
        <div><h2>Security</h2><p>Manage password and account access</p></div>
      </div>
      <button v-if="!changingPassword" class="password-button" type="button" :disabled="saving || verifyingEmail" @click="changingPassword = true">Change Password</button>
      <form v-else class="form-grid password-form" @submit.prevent="updatePassword">
        <label for="current-password">Current Password<input id="current-password" v-model="passwords.current_password" type="password" autocomplete="current-password" required :disabled="saving"></label>
        <label for="new-password">New Password<input id="new-password" v-model="passwords.new_password" type="password" autocomplete="new-password" minlength="6" maxlength="1024" required :disabled="saving"></label>
        <label for="confirm-password">Confirm New Password<input id="confirm-password" v-model="passwords.confirm_password" type="password" autocomplete="new-password" required :disabled="saving"></label>
        <div class="password-actions">
          <button class="cancel-button" type="button" :disabled="saving" @click="changingPassword = false; passwords.current_password = ''; passwords.new_password = ''; passwords.confirm_password = ''">Cancel</button>
          <button class="save-button" :disabled="saving">Update Password</button>
        </div>
      </form>
    </section>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="profileError" role="alert">{{ profileError }}</p>
    <button v-if="!loading && !loaded" class="cancel-button" type="button" @click="loadProfile">Retry</button>
    <button class="sign-out" type="button" :disabled="saving || authState.signingOut" @click="$emit('sign-out')">
      {{ authState.signingOut ? 'Signing out…' : 'Sign Out' }}
    </button>
    <p v-if="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.user-information { --info-blue: var(--primary-color, #287bf4); --info-panel: var(--bg-primary, #fff); --info-text: var(--text-primary, #171a22); color: var(--info-text); container-type: inline-size; }
.profile-details { margin: 0; }
.profile-summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.profile-summary > div { display: flex; min-width: 0; flex-direction: column; }
.profile-summary strong { overflow: hidden; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.profile-summary span { margin-top: 2px; color: var(--text-secondary, #7b8290); font-size: 12px; overflow-wrap: anywhere; }
.user-information button { cursor: pointer; font-family: inherit; }
.edit-button, .save-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; flex: 0 0 auto; min-height: 38px; padding: 0 14px; border: 0; border-radius: 10px; background: var(--info-blue); color: #fff; font-size: 12px; font-weight: 650; }
.form-section { padding: 19px; border: 1px solid var(--border-color, #e7eaf0); border-radius: 15px; background: var(--info-panel); }
.form-section + .form-section, .verification-form { margin-top: 14px; }
.section-heading, .security-copy { display: flex; align-items: center; gap: 11px; margin-bottom: 17px; }
.section-icon { display: grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; border-radius: 10px; background: var(--hover-bg, #eaf2ff); color: var(--info-blue); }
.section-heading h2, .security-copy h2 { margin: 0; font-size: 13px; font-weight: 700; }
.section-heading p, .security-copy p { margin: 2px 0 0; color: var(--text-secondary, #858b97); font-size: 11px; }
.form-grid { display: grid; gap: 13px; }
.form-grid.two-column { grid-template-columns: 1fr 1fr; }
.form-grid label { position: relative; display: flex; min-width: 0; flex-direction: column; gap: 6px; color: var(--text-secondary, #555d6a); font-size: 11px; font-weight: 650; }
.form-grid .full-field { grid-column: 1 / -1; }
.form-grid input, .form-grid textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--border-color, #dfe4ec); border-radius: 10px; outline: none; background: var(--info-panel); color: var(--info-text); font-family: inherit; font-size: 13px; font-weight: 450; transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease; }
.form-grid input { height: 40px; padding: 0 12px; }
.form-grid textarea { min-height: 76px; padding: 10px 12px 20px; resize: vertical; line-height: 1.45; }
.form-grid input:focus, .form-grid textarea:focus { border-color: var(--info-blue); box-shadow: 0 0 0 3px rgba(40,123,244,.12); }
.form-grid input:disabled, .form-grid textarea:disabled { border-color: transparent; background: var(--bg-secondary, #f5f7fa); color: var(--info-text); cursor: default; opacity: 1; -webkit-text-fill-color: var(--info-text); }
.form-grid small { position: absolute; right: 9px; bottom: 7px; color: var(--text-secondary, #9298a3); font-size: 9px; font-weight: 500; }
.profile-actions, .password-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 14px; }
.cancel-button, .password-button { min-height: 38px; padding: 0 14px; border: 1px solid var(--border-color, #dfe4ec); border-radius: 10px; background: var(--info-panel); color: var(--info-text); font-size: 12px; font-weight: 650; }
.security-section { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 14px; padding: 17px 18px; border: 1px solid var(--border-color, #e7eaf0); border-radius: 15px; background: var(--info-panel); }
.security-copy { min-width: 0; margin: 0; }
.password-form { width: 100%; }
.sign-out { width: 100%; margin-top: 14px; padding: 10px 20px; border: 1px solid #f1d5d8; border-radius: 10px; background: #fff7f7; color: #c83e4d; font-size: 13px; font-weight: 650; box-shadow: none; }
.sign-out:hover { background: #ffeded; }
.user-information button:disabled { cursor: default; opacity: .6; }
.user-information button:focus-visible { outline: 2px solid var(--info-blue); outline-offset: 3px; }
.user-information [role] { margin-top: 12px; overflow-wrap: anywhere; }
@container (max-width: 320px) { .form-grid.two-column { grid-template-columns: 1fr; } .profile-summary { align-items: flex-start; flex-direction: column; } .security-section { align-items: flex-start; flex-direction: column; } .password-actions { flex-wrap: wrap; } }
</style>
