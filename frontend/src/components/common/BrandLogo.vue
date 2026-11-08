<script setup lang="ts">
defineProps<{ size?: number }>()
</script>

<template>
  <span class="brand" :style="{ fontSize: `${size ?? 16}px` }">
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--ul-accent)" />
      <path
        d="M9 22c0-8 6-13 14-13-1 8-6 13-14 13Zm0 0 7-7"
        fill="none"
        stroke="#fff"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <span class="brand-name">Underleaf</span>
  </span>
</template>

<style scoped>
.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.5em;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ul-text);
}
.brand svg {
  width: 1.5em;
  height: 1.5em;
  flex-shrink: 0;
}
</style>
