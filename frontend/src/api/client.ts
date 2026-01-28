import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const apiKey = import.meta.env.VITE_API_KEY
  if (apiKey) {
    config.headers['x-api-key'] = apiKey
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      console.error(`[API] ${error.response.status} ${error.config?.method?.toUpperCase()} ${error.config?.url}`, error.response.data)
    } else if (error.request) {
      console.error('[API] No response (network/CORS error):', error.config?.url)
    } else {
      console.error('[API] Request setup error:', error.message)
    }
    return Promise.reject(error)
  }
)

export default apiClient
