import { Player } from "@remotion/player";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

function BankAIIntro() {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [0, 28], [0, 1], { extrapolateRight: "clamp" });
  const network = interpolate(frame, [18, 62], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 50%, #242443, #0c0c13 70%)", alignItems: "center", justifyContent: "center", color: "#f7f7fc", fontFamily: "Geist Variable, sans-serif" }}>
    <svg viewBox="0 0 600 220" style={{ position: "absolute", width: "100%", height: "100%", opacity: network }} aria-hidden="true">
      <g stroke="#7f87ee" strokeWidth="1.5" fill="none"><path d="M300 90 L115 165 M300 90 L235 180 M300 90 L365 180 M300 90 L485 165" /></g>
      {[115, 235, 365, 485].map((x, index) => <circle key={x} cx={x} cy={index === 0 || index === 3 ? 165 : 180} r="7" fill="#7f87ee" />)}
    </svg>
    <div style={{ zIndex: 1, textAlign: "center", transform: `translateY(${(1 - reveal) * 15}px)`, opacity: reveal }}><span style={{ fontSize: 42, fontWeight: 700, letterSpacing: "-.07em" }}>BankAI<span style={{ color: "#9399ff" }}>.</span></span><p style={{ margin: 0, fontSize: 12, letterSpacing: ".2em", color: "#a7a7bc" }}>AGENT WORKSPACE</p></div>
  </AbsoluteFill>;
}

export default function Intro() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return <div className="intro-player intro-static"><strong>BankAI.</strong><span>Supervisor · Account · Card · Loan · Support</span></div>;
  return <div className="intro-player"><Player component={BankAIIntro} compositionWidth={600} compositionHeight={220} durationInFrames={120} fps={30} controls autoPlay={false} style={{ width: "100%", aspectRatio: "600 / 220" }} /></div>;
}
