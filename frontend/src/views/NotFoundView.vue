<script setup lang="ts">
import { NButton, NResult } from 'naive-ui'
</script>

<template>
  <div class="not-found">
    <NResult status="404" title="页面不存在" description="你访问的页面不存在或已被移除。">
      <template #footer>
        <RouterLink to="/"><NButton type="primary">回到首页</NButton></RouterLink>
      </template>
    </NResult>
  </div>
</template>

<style scoped>
.not-found {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ul-bg);
}
</style>
