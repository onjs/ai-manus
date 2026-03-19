const DEFAULT_ERROR_MESSAGE = '任务执行失败，请稍后重试。';

export function formatAgentError(rawError: string | null | undefined): string {
  const raw = (rawError || '').trim();
  if (!raw) {
    return DEFAULT_ERROR_MESSAGE;
  }

  const normalized = raw.toLowerCase();

  if (normalized.includes('sandbox runner stream interrupted')) {
    return '与执行环境的连接中断，任务已停止。请点击“重试”继续。';
  }

  if (normalized.includes('failed to start sandbox runner')) {
    return '执行环境启动失败，请稍后重试。';
  }

  if (normalized.includes('gateway token expired')) {
    return '本次任务凭证已过期，任务已停止。请重新发起任务。';
  }

  if (normalized.includes('gateway runtime is not configured')) {
    return '运行配置缺失，暂时无法执行该任务。请联系管理员检查配置。';
  }

  if (normalized.includes('gateway stream failed') || normalized.includes('gateway runtime failed')) {
    return '模型服务暂时不可用，请稍后重试。';
  }

  if (normalized.includes('runner cancelled')) {
    return '执行环境已中断，任务已停止。请重试或重新发起任务。';
  }

  if (normalized.includes('invalid stream id specified as stream command argument')) {
    return '请求事件标识无效，任务未执行。请重试。';
  }

  if (normalized === 'no message') {
    return '未检测到可执行的任务内容，请补充后重试。';
  }

  if (normalized.startsWith('task error:')) {
    return '任务执行失败，请重试。如果持续失败，请联系管理员排查。';
  }

  return raw;
}
