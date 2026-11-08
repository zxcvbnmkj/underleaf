import { computed, ref, watchEffect } from 'vue'

const KEY = 'underleaf-theme'

function initial(): boolean {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved) return saved === 'dark'
  } catch {
    /* ignore */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

const isDark = ref(initial())

watchEffect(() => {
  document.documentElement.classList.toggle('dark', isDark.value)
})

/** 全局明暗主题（单例） */
export function useTheme() {
  return {
    isDark: computed(() => isDark.value),
    toggle() {
      isDark.value = !isDark.value
      try {
        localStorage.setItem(KEY, isDark.value ? 'dark' : 'light')
      } catch {
        /* ignore */
      }
    },
  }
}
