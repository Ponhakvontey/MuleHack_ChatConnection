<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { authRequest, authState } from '../services/auth.js'

const router = useRouter()
const code = ref('')
const error = ref('')
const busy = ref(false)
const resendAt = ref(Date.now() + (authState.challenge?.resend_in || 0) * 1000)
const clock = ref(Date.now())
const remaining = computed(() => Math.max(0, Math.ceil((resendAt.value - clock.value) / 1000)))
const timer = setInterval(() => { clock.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(timer))
async function verify() {
  error.value = ''; busy.value = true
  try {
    await authRequest('verify-otp', { code: code.value })
    authState.challenge = null
    await router.replace('/dashboard')
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function resend() {
  error.value = ''; busy.value = true
  try {
    const result = await authRequest('resend-otp', {})
    resendAt.value = Date.now() + result.resend_in * 1000
    code.value = ''
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="login-wrapper"><div class="login-card">
    <div class="brand-mark"><div class="brand-icon"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div><span class="brand-name">Talky</span></div>
    <h2>Verify your email</h2>
    <p class="subtitle">Enter the 6-digit code sent to your email. It expires in 5 minutes.</p>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <form @submit.prevent="verify">
      <div class="field-group"><label class="field-label" for="otp">Verification code</label><input v-model="code" id="otp" class="form-control" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required placeholder="000000"></div>
      <button type="submit" class="btn-login" :disabled="busy">{{ busy ? 'Please wait...' : 'Verify' }}</button>
    </form>
    <div class="divider"><span>or</span></div>
    <button class="btn-login" type="button" :disabled="busy || remaining > 0" @click="resend">{{ remaining ? `Resend code in ${remaining}s` : 'Resend code' }}</button>
    <RouterLink class="register-link" to="/login">Back to <strong>Sign in</strong></RouterLink>
  </div></div>
</template>
