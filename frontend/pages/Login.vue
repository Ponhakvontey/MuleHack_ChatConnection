<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authRequest, authState } from '../services/auth.js'
const router = useRouter()
const error = ref('')
const email = ref('')
const password = ref('')
const busy = ref(false)
async function submit() {
 error.value = ''; busy.value = true
 try {
  const result = await authRequest('login', { email: email.value, password: password.value })
  authState.challenge = { expires_in: result.expires_in, resend_in: result.resend_in }
  await router.push('/verify-otp')
 } catch (failure) { error.value = failure.message }
 finally { busy.value = false }
}
</script>

<template>
<div class="login-wrapper">
    <div class="login-card">

        <div class="brand-mark">
            <div class="brand-icon">
                <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            </div>
            <span class="brand-name">Talky</span>
        </div>

        <h2>Welcome back</h2>
        <p class="subtitle">Sign in to continue to your account</p>

        <template v-if="error">
        <div class="alert alert-danger">{{ error }}</div>
        </template>

        <form @submit.prevent="submit">
            <div class="field-group">
                <label class="field-label" for="email">Email</label>
                <input v-model="email" id="email" class="form-control" name="email" type="email" placeholder="Enter your email" autocomplete="username" required>
            </div>

            <div class="field-group">
                <label class="field-label" for="password">Password</label>
                <input v-model="password" required id="password" class="form-control" name="password" type="password" placeholder="••••••••" autocomplete="current-password">
            </div>

            <button type="submit" class="btn-login" :disabled="busy">{{ busy ? 'Signing in...' : 'Sign In' }}</button>
        </form>

        <div class="divider"><span>or</span></div>

        <RouterLink class="register-link" to="/register">
            Don't have an account? <strong>Create one</strong>
        </RouterLink>

    </div>
</div>
</template>
