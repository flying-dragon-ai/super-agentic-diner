// React Error Boundary: catches render errors in child components to prevent
// white-screen crashes. Shows a user-friendly fallback with retry button.
import { Component, type ReactNode, type ErrorInfo } from "react";

type Props = {
  children: ReactNode;
  fallback?: (error: Error, retry: () => void) => ReactNode;
};

type State = { error: Error | null };

export class SceneErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log to console for debugging; in production this would go to a service.
    console.error("[SceneErrorBoundary] 3D scene crashed:", error, info.componentStack);
  }

  retry = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.retry);
      }
      return (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            background: "#0b0f14",
            color: "#dfe8f5",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <div style={{ fontSize: 48 }}>⚠️</div>
          <div style={{ fontSize: 18, color: "#f0c060" }}>3D 场景渲染异常</div>
          <div style={{ fontSize: 13, color: "#9fb6d8", maxWidth: 400, textAlign: "center" }}>
            场景遇到了渲染问题。这通常是由于 GPU 内存不足或浏览器 WebGL 兼容性导致的。
            <br />
            点击重试可以恢复场景，或访问简化版大屏。
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              onClick={this.retry}
              style={{
                padding: "8px 20px",
                background: "rgba(240,192,96,0.2)",
                border: "1px solid rgba(240,192,96,0.5)",
                borderRadius: 8,
                color: "#f0c060",
                cursor: "pointer",
                fontSize: 14,
              }}
            >
              重试
            </button>
            <a
              href="/3d/dashboard"
              style={{
                padding: "8px 20px",
                background: "rgba(127,166,216,0.15)",
                border: "1px solid rgba(127,166,216,0.3)",
                borderRadius: 8,
                color: "#7fa6d8",
                textDecoration: "none",
                fontSize: 14,
              }}
            >
              查看大屏
            </a>
          </div>
          <details style={{ marginTop: 8, maxWidth: 500, fontSize: 11, opacity: 0.6 }}>
            <summary style={{ cursor: "pointer", color: "#7fa6d8" }}>技术详情</summary>
            <pre style={{ marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {this.state.error.message}
              {"\n"}
              {this.state.error.stack?.slice(0, 500)}
            </pre>
          </details>
        </div>
      );
    }
    return this.props.children;
  }
}
