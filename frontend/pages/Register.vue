<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { authRequest } from '../services/auth.js'
const router = useRouter()
const error = ref('')
const email = ref('')
const username = ref('')
const busy = ref(false)
async function submit() {
 error.value = ''; busy.value = true
 try {
  await authRequest('register', { username: username.value, email: email.value, password: password.value })
  await router.push('/login')
 } catch (failure) { error.value = failure.message }
 finally { busy.value = false }
}
const password = ref('')
const hint = computed(() => {
 const v = password.value
 if (!v.length) return { text: 'At least 6 characters — not all the same digit', error: false, color: '' }
 if (v.length < 6) return { text: `${6 - v.length} more character${6 - v.length > 1 ? 's' : ''} needed`, error: true, color: '' }
 if (/^\d+$/.test(v) && new Set(v).size === 1) return { text: 'Cannot be all the same digit', error: true, color: '' }
 return { text: '✓ Looks good', error: false, color: '#2860b0' }
})
</script>

<template>
<div class="register-wrapper">
    <div class="register-card">

        <div class="brand-mark">
            <div class="brand-icon">
                <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            </div>
            <span class="brand-name">Talky</span>
        </div>

        <h2>Create account</h2>
        <p class="subtitle">Join us — it only takes a moment</p>

        <form @submit.prevent="submit">
            <div class="field-group">
                <label class="field-label" for="username">Username</label>
                <input v-model="username" required id="username" class="form-control" name="username" placeholder="Choose a username" autocomplete="username">
            </div>

            <div class="field-group">
                <label class="field-label" for="email">Email</label>
                <input v-model="email" required id="email" class="form-control" name="email" type="email" placeholder="Enter your email" autocomplete="email">
            </div>

            <div class="field-group">
                <label class="field-label" for="password">Password</label>
                <input required v-model="password" id="password" class="form-control" name="password" type="password" placeholder="••••••••" autocomplete="new-password">
                <p class="field-hint" :class="{ error: hint.error }" :style="{ color: hint.color }" id="passwordHint">{{ hint.text }}</p>
            </div>

            <button type="submit" class="btn-register" :disabled="busy">{{ busy ? 'Please wait...' : 'Create Account' }}</button>
        </form>

        <template v-if="error">
        <div class="alert alert-danger">{{ error }}</div>
        </template>

        <div class="divider"><span>or</span></div>

        <RouterLink class="login-link" to="/login">
            Already have an account? <strong>Sign in</strong>
        </RouterLink>

        <p class="terms-note">By creating an account you agree to our<br>Terms of Service &amp; Privacy Policy.</p>

    </div>
</div>
</template>
