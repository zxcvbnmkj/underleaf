<script setup lang="ts">
import { computed } from 'vue'
import {
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  darkTheme,
  dateZhCN,
  zhCN,
  type GlobalThemeOverrides,
} from 'naive-ui'
import { useTheme } from '@/composables/useTheme'

const { isDark } = useTheme()

const FONT = `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif`

const overrides = computed<GlobalThemeOverrides>(() => {
  const accent = isDark.value
    ? {
        primaryColor: '#4fb27f',
        primaryColorHover: '#63c290',
        primaryColorPressed: '#3f9a6b',
        primaryColorSuppl: '#4fb27f',
      }
    : {
        primaryColor: '#2f855a',
        primaryColorHover: '#38a169',
        primaryColorPressed: '#276749',
        primaryColorSuppl: '#38a169',
      }
  return {
    common: { ...accent, fontFamily: FONT, borderRadius: '6px' },
    Tree: { nodeHeight: '30px' },
  }
})
</script>

<template>
  <NConfigProvider
    :theme="isDark ? darkTheme : null"
    :theme-overrides="overrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <NMessageProvider>
      <NDialogProvider>
        <RouterView />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
