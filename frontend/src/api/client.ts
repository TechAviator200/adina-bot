import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://adina-bot-backend.onrender.com'
const API_KEY = import.meta.env.VITE_API_KEY

// Warn in development if API key is missing
if (!API_KEY && import.meta.env.DEV) {
  console.warn('[API] VITE_API_KEY not set - API requests will fail with 401')
}

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Always attach x-api-key header if available
apiClient.interceptors.request.use((config) => {
  if (API_KEY) {
    config.headers['x-api-key'] = API_KEY
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const status = error.response.status
      const url = error.config?.url
      const method = error.config?.method?.toUpperCase()

      if (status === 401) {
        console.error(`[API] 401 Unauthorized - Check that VITE_API_KEY matches backend API_KEY`)
      }
      console.error(`[API] ${status} ${method} ${url}`, error.response.data)
    } else if (error.request) {
      console.error('[API] No response (network/CORS error):', error.config?.url)
    } else {
      console.error('[API] Request setup error:', error.message)
    }
    return Promise.reject(error)
  }
)

export default apiClient
