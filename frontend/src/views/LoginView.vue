<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputGroup,
  NTabPane,
  NTabs,
  useMessage,
  type FormInst,
  type FormRules,
} from 'naive-ui'
import { ArrowLeft, Moon, Sun } from 'lucide-vue-next'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import BrandLogo from '@/components/common/BrandLogo.vue'
import SendCodeButton from '@/components/common/SendCodeButton.vue'
import { EMAIL_RE } from '@/utils/format'
import type { User } from '@/types'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const { isDark, toggle: toggleTheme } = useTheme()

type Tab = 'password' | 'code' | 'register'
type Mode = Tab | 'reset'
const tab = ref<Tab>(route.query.tab === 'register' ? 'register' : 'password')
const mode = ref<Mode>(tab.value)
const submitting = ref(false)

// 邮箱在各表单间共享，切换方式时不用重复输入；密码登录的账号可以是邮箱或昵称
const email = ref('')
const pwdForm = ref({ account: '', password: '' })
const codeForm = ref({ code: '' })
const registerForm = ref({ code: '', nickname: '', password: '', confirm: '' })
const resetForm = ref({ code: '', newPassword: '', confirm: '' })

const pwdRef = ref<FormInst>()
const codeRef = ref<FormInst>()
const registerRef = ref<FormInst>()
const resetRef = ref<FormInst>()

// 校验规则与后端一致（backend/app/schemas/auth.py）
const NICKNAME_RE = /^[A-Za-z0-9_\-\u3400-\u4dbf\u4e00-\u9fff]{2,20}$/
const emailRule = {
  trigger: 'blur',
  validator: () => {
    if (!email.value.trim()) return new Error('请输入邮箱')
    if (!EMAIL_RE.test(email.value.trim())) return new Error('邮箱格式不正确')
    return true
  },
}
const codeRule = [
  { required: true, message: '请输入验证码', trigger: 'blur' },
  { pattern: /^\d{6}$/, message: '验证码为 6 位数字', trigger: 'blur' },
]
const newPasswordRule = [
  { required: true, message: '请输入密码', trigger: 'blur' },
  { min: 8, message: '密码至少 8 个字符', trigger: 'blur' },
]
const confirmRule = (get: () => string) => ({
  trigger: ['blur', 'input'],
  validator: (_r: unknown, v: string) => (v === get() ? true : new Error('两次输入的密码不一致')),
})

const pwdRules: FormRules = {
  account: { required: true, message: '请输入邮箱或昵称', trigger: 'blur' },
  password: { required: true, message: '请输入密码', trigger: 'blur' },
}
const codeRules: FormRules = { email: emailRule, code: codeRule }
const registerRules: FormRules = {
  email: emailRule,
  code: codeRule,
  nickname: {
    trigger: 'blur',
    validator: (_r: unknown, v: string) =>
      NICKNAME_RE.test(v.trim())
        ? true
        : new Error('昵称为 2～20 个字符，只能包含中文、字母、数字、_ 和 -'),
  },
  password: newPasswordRule,
  confirm: confirmRule(() => registerForm.value.password),
}
const resetRules: FormRules = {
  email: emailRule,
  code: codeRule,
  newPassword: newPasswordRule,
  confirm: confirmRule(() => resetForm.value.newPassword),
}

async function run(form: FormInst | undefined, action: () => Promise<void>) {
  try {
    await form?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await action()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

function onLoggedIn(user: User) {
  auth.setUser(user)
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/notes'
  router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/notes')
}

const loginWithPassword = () =>
  run(pwdRef.value, async () =>
    onLoggedIn(
      await authApi.loginWithPassword(pwdForm.value.account.trim(), pwdForm.value.password),
    ),
  )

const loginWithCode = () =>
  run(codeRef.value, async () =>
    onLoggedIn(await authApi.loginWithCode(email.value.trim(), codeForm.value.code)),
  )

const register = () =>
  run(registerRef.value, async () => {
    const user = await authApi.register({
      email: email.value.trim(),
      code: registerForm.value.code,
      nickname: registerForm.value.nickname.trim(),
      password: registerForm.value.password,
    })
    message.success(`注册成功，欢迎你，${user.nickname}`)
    onLoggedIn(user)
  })

const resetPassword = () =>
  run(resetRef.value, async () => {
    await authApi.resetPassword(
      email.value.trim(),
      resetForm.value.code,
      resetForm.value.newPassword,
    )
    message.success('密码已重置，请使用新密码登录')
    pwdForm.value = { account: email.value.trim(), password: '' }
    resetForm.value = { code: '', newPassword: '', confirm: '' }
    switchTo('password')
  })

function switchTo(next: Mode) {
  // 已在密码登录中填了邮箱时，带到其他表单
  if (next !== 'password' && !email.value && pwdForm.value.account.includes('@'))
    email.value = pwdForm.value.account.trim()
  if (next !== 'reset') tab.value = next
  mode.value = next
}
</script>

<template>
  <div class="login-page">
    <button
      class="theme-toggle"
      :aria-label="isDark ? '浅色模式' : '深色模式'"
      @click="toggleTheme"
    >
      <NIcon :size="18"><Sun v-if="isDark" /><Moon v-else /></NIcon>
    </button>

    <div class="login-card">
      <div class="login-head">
        <BrandLogo :size="22" />
        <p class="tagline">左边写 Markdown，右边看效果，笔记随时随地同步</p>
      </div>

      <template v-if="mode !== 'reset'">
        <NTabs
          :value="tab"
          type="line"
          justify-content="space-evenly"
          animated
          @update:value="switchTo"
        >
          <NTabPane name="password" tab="密码登录">
            <NForm
              ref="pwdRef"
              :model="pwdForm"
              :rules="pwdRules"
              @submit.prevent="loginWithPassword"
            >
              <NFormItem path="account" :show-label="false">
                <NInput
                  v-model:value="pwdForm.account"
                  placeholder="邮箱或昵称"
                  :input-props="{ autocomplete: 'username' }"
                />
              </NFormItem>
              <NFormItem path="password" :show-label="false">
                <NInput
                  v-model:value="pwdForm.password"
                  type="password"
                  show-password-on="click"
                  placeholder="密码"
                  :input-props="{ autocomplete: 'current-password' }"
                />
              </NFormItem>
              <NButton type="primary" block attr-type="submit" :loading="submitting">登录</NButton>
              <div class="form-links">
                <a href="#" @click.prevent="switchTo('reset')">忘记密码？</a>
                <a href="#" @click.prevent="switchTo('register')">没有账号？注册</a>
              </div>
            </NForm>
          </NTabPane>

          <NTabPane name="code" tab="验证码登录">
            <NForm
              ref="codeRef"
              :model="{ email, ...codeForm }"
              :rules="codeRules"
              @submit.prevent="loginWithCode"
            >
              <NFormItem path="email" :show-label="false">
                <NInput
                  v-model:value="email"
                  placeholder="邮箱"
                  :input-props="{ type: 'email', autocomplete: 'email' }"
                />
              </NFormItem>
              <NFormItem path="code" :show-label="false">
                <NInputGroup>
                  <NInput
                    v-model:value="codeForm.code"
                    placeholder="6 位验证码"
                    maxlength="6"
                    :input-props="{ inputmode: 'numeric', autocomplete: 'one-time-code' }"
                  />
                  <SendCodeButton :email="email" purpose="login" />
                </NInputGroup>
              </NFormItem>
              <NButton type="primary" block attr-type="submit" :loading="submitting">登录</NButton>
              <div class="form-links center">
                <a href="#" @click.prevent="switchTo('register')">还没有账号？注册</a>
              </div>
            </NForm>
          </NTabPane>

          <NTabPane name="register" tab="注册">
            <NForm
              ref="registerRef"
              :model="{ email, ...registerForm }"
              :rules="registerRules"
              @submit.prevent="register"
            >
              <NFormItem path="email" :show-label="false">
                <NInput
                  v-model:value="email"
                  placeholder="邮箱"
                  :input-props="{ type: 'email', autocomplete: 'email' }"
                />
              </NFormItem>
              <NFormItem path="code" :show-label="false">
                <NInputGroup>
                  <NInput
                    v-model:value="registerForm.code"
                    placeholder="6 位验证码"
                    maxlength="6"
                    :input-props="{ inputmode: 'numeric', autocomplete: 'one-time-code' }"
                  />
                  <SendCodeButton :email="email" purpose="register" />
                </NInputGroup>
              </NFormItem>
              <NFormItem path="nickname" :show-label="false">
                <NInput
                  v-model:value="registerForm.nickname"
                  placeholder="昵称（2～20 个字符，可用于登录）"
                  maxlength="20"
                  :input-props="{ autocomplete: 'nickname' }"
                />
              </NFormItem>
              <NFormItem path="password" :show-label="false">
                <NInput
                  v-model:value="registerForm.password"
                  type="password"
                  show-password-on="click"
                  placeholder="密码（至少 8 个字符）"
                  :input-props="{ autocomplete: 'new-password' }"
                />
              </NFormItem>
              <NFormItem path="confirm" :show-label="false">
                <NInput
                  v-model:value="registerForm.confirm"
                  type="password"
                  show-password-on="click"
                  placeholder="确认密码"
                  :input-props="{ autocomplete: 'new-password' }"
                />
              </NFormItem>
              <NButton type="primary" block attr-type="submit" :loading="submitting"
                >注册并登录</NButton
              >
              <div class="form-links center">
                <a href="#" @click.prevent="switchTo('password')">已有账号？登录</a>
              </div>
            </NForm>
          </NTabPane>
        </NTabs>
      </template>

      <template v-else>
        <button class="back-link" @click="switchTo('password')">
          <NIcon><ArrowLeft /></NIcon> 返回登录
        </button>
        <h2 class="reset-title">重置密码</h2>
        <NForm
          ref="resetRef"
          :model="{ email, ...resetForm }"
          :rules="resetRules"
          @submit.prevent="resetPassword"
        >
          <NFormItem path="email" :show-label="false">
            <NInput
              v-model:value="email"
              placeholder="注册邮箱"
              :input-props="{ type: 'email', autocomplete: 'email' }"
            />
          </NFormItem>
          <NFormItem path="code" :show-label="false">
            <NInputGroup>
              <NInput
                v-model:value="resetForm.code"
                placeholder="6 位验证码"
                maxlength="6"
                :input-props="{ inputmode: 'numeric', autocomplete: 'one-time-code' }"
              />
              <SendCodeButton :email="email" purpose="reset_password" />
            </NInputGroup>
          </NFormItem>
          <NFormItem path="newPassword" :show-label="false">
            <NInput
              v-model:value="resetForm.newPassword"
              type="password"
              show-password-on="click"
              placeholder="新密码（至少 8 个字符）"
              :input-props="{ autocomplete: 'new-password' }"
            />
          </NFormItem>
          <NFormItem path="confirm" :show-label="false">
            <NInput
              v-model:value="resetForm.confirm"
              type="password"
              show-password-on="click"
              placeholder="确认新密码"
              :input-props="{ autocomplete: 'new-password' }"
            />
          </NFormItem>
          <NButton type="primary" block attr-type="submit" :loading="submitting">重置密码</NButton>
        </NForm>
      </template>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background:
    radial-gradient(1200px 600px at 10% -10%, var(--ul-accent-soft), transparent 60%),
    var(--ul-bg-soft);
}
.theme-toggle {
  position: fixed;
  top: 16px;
  right: 16px;
  display: inline-flex;
  padding: 8px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ul-text-2);
  cursor: pointer;
}
.theme-toggle:hover {
  background: var(--ul-bg-mute);
}
.login-card {
  width: min(400px, 100%);
  padding: 32px 28px 28px;
  border: 1px solid var(--ul-border);
  border-radius: 14px;
  background: var(--ul-bg);
  box-shadow: 0 12px 40px rgb(0 0 0 / 0.06);
}
.login-head {
  text-align: center;
  margin-bottom: 20px;
}
.tagline {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--ul-text-2);
}
.login-card :deep(.n-tabs-pane-wrapper) {
  padding-top: 12px;
}
.form-links {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 13px;
}
.form-links.center {
  justify-content: center;
}
.form-links a {
  color: var(--ul-accent);
  text-decoration: none;
}
.form-links a:hover {
  text-decoration: underline;
}
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ul-text-2);
  font-size: 13px;
  cursor: pointer;
}
.back-link:hover {
  color: var(--ul-text);
}
.reset-title {
  margin: 12px 0 16px;
  font-size: 18px;
}
</style>
