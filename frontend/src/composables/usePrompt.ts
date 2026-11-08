import { h, ref } from 'vue'
import { NInput, useDialog } from 'naive-ui'

interface PromptOptions {
  title: string
  value?: string
  placeholder?: string
  positiveText?: string
}

/** 弹出带输入框的对话框，确认返回输入内容，取消返回 null */
export function usePrompt() {
  const dialog = useDialog()

  return (opts: PromptOptions) =>
    new Promise<string | null>((resolve) => {
      const value = ref(opts.value ?? '')
      let settled = false
      const finish = (result: string | null) => {
        if (settled) return
        settled = true
        resolve(result)
      }

      const d = dialog.create({
        title: opts.title,
        showIcon: false,
        positiveText: opts.positiveText ?? '确定',
        negativeText: '取消',
        content: () =>
          h(NInput, {
            value: value.value,
            placeholder: opts.placeholder,
            autofocus: true,
            maxlength: 100,
            'onUpdate:value': (v: string) => (value.value = v),
            onKeydown: (e: KeyboardEvent) => {
              if (e.key === 'Enter' && !e.isComposing && value.value.trim()) {
                finish(value.value.trim())
                d.destroy()
              }
            },
          }),
        onPositiveClick: () => {
          if (!value.value.trim()) return false
          finish(value.value.trim())
        },
        onAfterLeave: () => finish(null),
      })
    })
}
