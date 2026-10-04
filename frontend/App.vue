<script setup>
import { watch, ref } from 'vue'
import { useRoute } from 'vue-router'
import { router } from './router.js'
import loginCss from './styles/login.css?raw'
import registerCss from './styles/register.css?raw'
import dashboardCss from './styles/dashboard.css?raw'

const route = useRoute()
const error = ref('')
router.onError(() => { error.value = 'Unable to connect. Please reload to try again.' })
watch(() => route.path, path => {
  const dashboard = path === '/dashboard'
  let style = document.getElementById('page-style')
  if (!style) { style = document.createElement('style'); style.id = 'page-style'; document.head.appendChild(style) }
  style.textContent = dashboard ? dashboardCss : path === '/register' ? registerCss : loginCss
  for (const [id, href, enabled] of [
    ['bootstrap-style', 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css', !dashboard],
    ['chat-style', '/static/assets/css/style.css', dashboard]
  ]) {
    let link = document.getElementById(id)
    if (!enabled) { link?.remove(); continue }
    if (!link) { link = document.createElement('link'); link.id = id; link.rel = 'stylesheet'; link.href = href; document.head.insertBefore(link, style) }
  }
  let viewport = document.querySelector('meta[name=viewport]')
  if (!dashboard) viewport?.remove()
  else if (!viewport) { viewport = document.createElement('meta'); viewport.name = 'viewport'; viewport.content = 'width=device-width, initial-scale=1.0'; document.head.appendChild(viewport) }
  if (dashboard) document.body.setAttribute('data-theme', 'light')
  else document.body.removeAttribute('data-theme')
  document.title = dashboard ? 'Premium Chat UI' : path === '/register' ? 'Register' : path === '/verify-otp' ? 'Verify OTP' : 'Login'
}, { immediate: true })
</script>

<template>
  <div v-if="error" class="login-wrapper"><div class="login-card"><div class="alert alert-danger">{{ error }}</div></div></div>
  <RouterView v-else />
</template>
