import { Component, type ReactNode } from 'react';

export class ErrorBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="boot-screen"><section className="recovery-message" role="alert"><h1>工作台暂时无法显示</h1><p>已保存的协作仍然保留。请重新加载页面。</p><button onClick={()=>location.reload()}>重新加载</button></section></main>;
    return this.props.children;
  }
}
