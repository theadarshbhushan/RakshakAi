import { create } from 'zustand'
import { api, setAccessToken } from '@/api/client'
import type { MeResponse, Role, UserSummary } from '@/api/types'

interface AuthState {
  user: UserSummary | null
  org: { id?: string; name?: string; slug?: string; plan?: string } | null
  permissions: string[]
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
  initAuth: () => Promise<boolean>
  hasRole: (...roles: Role[]) => boolean
  can: (permission: string) => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  org: null,
  permissions: [],
  isAuthenticated: false,
  isLoading: true,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.auth.login({ email, password })
      setAccessToken(res.access_token)

      // Fetch profile and permissions
      const me: MeResponse = await api.auth.me()
      set({
        user: {
          id: me.id,
          email: me.email,
          full_name: me.full_name,
          role: me.role,
          org_id: me.org_id,
          is_active: true,
        },
        org: {
          id: me.org_id,
          name: me.org_name,
          slug: me.org_slug,
          plan: me.plan,
        },
        permissions: me.permissions || [],
        isAuthenticated: true,
        isLoading: false,
        error: null,
      })
    } catch (err: any) {
      set({
        user: null,
        org: null,
        permissions: [],
        isAuthenticated: false,
        isLoading: false,
        error: err.message || 'Login failed',
      })
      throw err
    }
  },

  logout: async () => {
    try {
      await api.auth.logout()
    } catch {
      // Ignore network errors on logout
    } finally {
      setAccessToken(null)
      set({
        user: null,
        org: null,
        permissions: [],
        isAuthenticated: false,
        isLoading: false,
        error: null,
      })
    }
  },

  refreshMe: async () => {
    try {
      const me: MeResponse = await api.auth.me()
      set({
        user: {
          id: me.id,
          email: me.email,
          full_name: me.full_name,
          role: me.role,
          org_id: me.org_id,
          is_active: true,
        },
        org: {
          id: me.org_id,
          name: me.org_name,
          slug: me.org_slug,
          plan: me.plan,
        },
        permissions: me.permissions || [],
        isAuthenticated: true,
      })
    } catch {
      setAccessToken(null)
      set({
        user: null,
        org: null,
        permissions: [],
        isAuthenticated: false,
      })
    }
  },

  initAuth: async () => {
    set({ isLoading: true })
    try {
      const refreshRes = await api.auth.refresh()
      if (refreshRes && refreshRes.access_token) {
        setAccessToken(refreshRes.access_token)
        const me: MeResponse = await api.auth.me()
        set({
          user: {
            id: me.id,
            email: me.email,
            full_name: me.full_name,
            role: me.role,
            org_id: me.org_id,
            is_active: true,
          },
          org: {
            id: me.org_id,
            name: me.org_name,
            slug: me.org_slug,
            plan: me.plan,
          },
          permissions: me.permissions || [],
          isAuthenticated: true,
          isLoading: false,
        })
        return true
      }
    } catch {
      // Not logged in or expired cookie
    }
    set({
      user: null,
      org: null,
      permissions: [],
      isAuthenticated: false,
      isLoading: false,
    })
    return false
  },

  hasRole: (...roles: Role[]) => {
    const currentRole = get().user?.role as Role
    if (!currentRole) return false
    return roles.includes(currentRole)
  },

  can: (permission: string) => {
    const permissions = get().permissions
    return permissions.includes(permission) || permissions.includes('*')
  },
}))
