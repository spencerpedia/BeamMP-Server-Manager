import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'
import '@xterm/xterm/css/xterm.css'

createApp(App).use(router).mount('#app')
