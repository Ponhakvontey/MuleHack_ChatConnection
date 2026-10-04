import { createRouter, createWebHistory } from 'vue-router'
import { refreshSession } from './services/auth.js'
import Login from './pages/Login.vue'
import Register from './pages/Register.vue'
import VerifyOtp from './pages/VerifyOtp.vue'
import DashboardRoute from './pages/DashboardRoute.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: Login },
    { path: '/register', component: Register },
    { path: '/verify-otp', component: VerifyOtp },
    { path: '/dashboard', component: DashboardRoute, meta: { requiresAuth: true } },
    { path: '/:pathMatch(.*)*', redirect: '/login' }
  ]
})

router.beforeEach(async to => {
  const state = await refreshSession()
  if (to.meta.requiresAuth && !state.user) return state.challenge ? '/verify-otp' : '/login'
  if (to.path === '/verify-otp' && !state.challenge && !state.user) return '/login'
  if (state.user && ['/login', '/register', '/verify-otp'].includes(to.path)) return '/dashboard'
})
