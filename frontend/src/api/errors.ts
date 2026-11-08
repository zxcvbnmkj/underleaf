/** 与后端统一错误格式 { code, message, detail } 对应 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message)
  }
}
