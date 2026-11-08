export const WELCOME_CONTENT = `# 欢迎使用 Underleaf

左边写 Markdown，右边实时预览。内容会**自动保存**，换一台设备打开也是最新的。

## 支持的语法

### 列表与任务

- 无序列表
  - 嵌套列表
1. 有序列表
2. 第二项

- [x] 搭好前端界面
- [ ] 接入后端
- [ ] 导出 PDF / Word

### 表格

| 功能 | 状态 | 说明 |
|:---|:---:|---:|
| 编辑与预览 | ✅ | 同步滚动 |
| 只读分享 | ✅ | 链接永久有效 |
| 导出 | 🚧 | 需要后端 |

### 代码高亮

\`\`\`ts
interface Note {
  id: number
  title: string
  content: string
}

const greet = (name: string) => \`你好，\${name}\`
\`\`\`

\`\`\`python
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/v1/notes")
async def list_notes():
    return []
\`\`\`

### 数学公式

行内公式：质能方程 $E = mc^2$，欧拉恒等式 $e^{i\\pi} + 1 = 0$。

块级公式：

$$
\\int_{-\\infty}^{\\infty} e^{-x^2}\\,dx = \\sqrt{\\pi}
$$

$$
\\begin{aligned}
\\nabla \\cdot \\mathbf{E} &= \\frac{\\rho}{\\varepsilon_0} \\\\
\\nabla \\times \\mathbf{B} &= \\mu_0 \\mathbf{J} + \\mu_0 \\varepsilon_0 \\frac{\\partial \\mathbf{E}}{\\partial t}
\\end{aligned}
$$

### 流程图（Mermaid）

\`\`\`mermaid
flowchart LR
  A[编辑笔记] --> B{自动保存}
  B -->|版本一致| C[保存成功]
  B -->|版本冲突| D[提示用户选择]
\`\`\`

### 引用

> 线上托管笔记，避免跨设备进度不同步，也不怕丢失。

---

试试右上角的 **分享** 按钮，打开公开分享后可以把链接发给别人只读查看。
`

export const DRAFT_CONTENT = `# 读书笔记

## 《程序员修炼之道》

> 不要容忍破窗户。

- 关注代码质量，发现小问题立即修复
- DRY：不要重复自己
`
