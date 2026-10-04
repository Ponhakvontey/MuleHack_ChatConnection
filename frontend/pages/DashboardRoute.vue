<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Dashboard from './Dashboard.vue'
import { backendFetch } from '../services/auth.js'

const route = useRoute()
const data = ref(null)
const error = ref('')
onMounted(async () => {
  try {
    const query = route.query.chat_user ? '?chat_user=' + encodeURIComponent(route.query.chat_user) : ''
    const response = await backendFetch('/api/dashboard' + query)
    const result = await response.json()
    if (!response.ok) throw new Error(result.error || 'Unable to load messages.')
    data.value = result
  } catch (failure) { error.value = failure.message }
})
</script>

<template>
  <Dashboard v-if="data" v-bind="data" />
  <div v-else role="status">{{ error || 'Loading...' }}</div>
</template>
