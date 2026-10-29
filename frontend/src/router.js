import { createRouter, createWebHistory } from 'vue-router'
import { store, loadUser } from './store'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', component: () => import('./views/Dashboard.vue') },
  {
    path: '/servers/:id',
    component: () => import('./views/ServerView.vue'),
    props: (r) => ({ id: Number(r.params.id) }),
    children: [
      { path: '', redirect: (to) => `/servers/${to.params.id}/console` },
      { path: 'console', component: () => import('./views/tabs/ConsoleTab.vue') },
      { path: 'config', component: () => import('./views/tabs/ConfigTab.vue') },
      { path: 'mods', component: () => import('./views/tabs/ModsTab.vue') },
      { path: 'plugins', component: () => import('./views/tabs/PluginsTab.vue') },
      { path: 'players', component: () => import('./views/tabs/PlayersTab.vue') },
      { path: 'metrics', component: () => import('./views/tabs/MetricsTab.vue') },
      { path: 'schedules', component: () => import('./views/tabs/SchedulesTab.vue') },
      { path: 'backups', component: () => import('./views/tabs/BackupsTab.vue') },
      { path: 'settings', component: () => import('./views/tabs/SettingsTab.vue') },
    ],
  },
  { path: '/admin/users', component: () => import('./views/Users.vue'), meta: { admin: true } },
  { path: '/admin/versions', component: () => import('./views/Versions.vue'), meta: { admin: true } },
  { path: '/admin/audit', component: () => import('./views/Audit.vue'), meta: { admin: true } },
  { path: '/admin/templates', component: () => import('./views/Templates.vue'), meta: { admin: true } },
  { path: '/admin/import', component: () => import('./views/Import.vue'), meta: { admin: true } },
  { path: '/account', component: () => import('./views/Account.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  if (!store.loaded) await loadUser()
  if (!to.meta.public && !store.user) return { path: '/login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (to.meta.admin && store.user?.role !== 'admin') return '/'
})

window.addEventListener('bmsm:unauthorized', () => {
  store.user = null
  if (router.currentRoute.value.path !== '/login') router.push('/login')
})

export default router
