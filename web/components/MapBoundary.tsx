"use client";
import { Component, type ReactNode } from "react";

/** Keep neighborhood controls usable if WebGL fails to initialize. */
export default class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="map-loading" role="status">
      <div style={{ padding: 24, maxWidth: 400 }}>
        <h2>Map view unavailable</h2>
        <p>You can still search neighborhoods, view forecasts, and submit observations using the controls on this page.</p>
        <button className="observation-button" onClick={() => this.setState({ failed: false })}>Retry map</button>
      </div>
    </div>;
    return this.props.children;
  }
}
