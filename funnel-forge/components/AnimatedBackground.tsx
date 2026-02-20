"use client";

import { useEffect, useRef } from "react";

export default function AnimatedBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let w = 0;
    let h = 0;

    const resize = () => {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    /* ── Colors ── */
    const TEAL_1 = [45, 212, 191];   // #2dd4bf
    const TEAL_2 = [14, 165, 233];   // #0ea5e9
    const BG = [13, 15, 20];         // #0d0f14

    const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
    const rgb = (c: number[], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
    const lerpColor = (t: number) => TEAL_1.map((v, i) => Math.round(lerp(v, TEAL_2[i], t)));

    /* ── Particles ── */
    interface Particle {
      x: number; y: number; r: number;
      vx: number; vy: number;
      alpha: number; pulse: number; speed: number;
    }

    const particles: Particle[] = Array.from({ length: 60 }, () => ({
      x: Math.random() * 2000,
      y: Math.random() * 2000,
      r: Math.random() * 1.8 + 0.4,
      vx: (Math.random() - 0.5) * 0.3,
      vy: -Math.random() * 0.25 - 0.05,
      alpha: Math.random() * 0.3 + 0.05,
      pulse: Math.random() * Math.PI * 2,
      speed: Math.random() * 0.01 + 0.005,
    }));

    /* ── Bezier S-curve path ── */
    function bezierPoint(t: number): { x: number; y: number } {
      // S-curve using two cubic segments
      const padX = w * 0.08;
      const padY = h * 0.12;

      if (t <= 0.5) {
        const lt = t * 2;
        const p0 = { x: padX, y: h * 0.3 };
        const p1 = { x: w * 0.35, y: padY * 0.5 };
        const p2 = { x: w * 0.55, y: h * 0.55 };
        const p3 = { x: w * 0.5, y: h * 0.5 };
        return cubicBez(p0, p1, p2, p3, lt);
      } else {
        const lt = (t - 0.5) * 2;
        const p0 = { x: w * 0.5, y: h * 0.5 };
        const p1 = { x: w * 0.45, y: h * 0.45 };
        const p2 = { x: w * 0.65, y: h - padY * 0.5 };
        const p3 = { x: w - padX, y: h * 0.7 };
        return cubicBez(p0, p1, p2, p3, lt);
      }
    }

    function cubicBez(
      p0: { x: number; y: number }, p1: { x: number; y: number },
      p2: { x: number; y: number }, p3: { x: number; y: number },
      t: number
    ) {
      const u = 1 - t;
      return {
        x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x,
        y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y,
      };
    }

    /* ── Trail ── */
    interface TrailPoint { x: number; y: number; age: number }
    const trail: TrailPoint[] = [];
    const TRAIL_MAX = 80;

    /* ── Water drop state ── */
    let dropPhase = 0;    // 0 = flying, 1 = diving, 2 = drop glow, 3 = fade
    let dropTimer = 0;
    let dropX = 0;
    let dropY = 0;
    let dropAlpha = 0;
    let dropScale = 0;

    /* ── Plane state ── */
    const CYCLE = 8;      // seconds per loop
    let elapsed = 0;
    let prevTime = performance.now();

    /* ── Draw paper airplane ── */
    function drawPlane(x: number, y: number, angle: number, size: number, alpha: number) {
      ctx!.save();
      ctx!.translate(x, y);
      ctx!.rotate(angle);
      ctx!.globalAlpha = alpha;

      const grad = ctx!.createLinearGradient(-size, 0, size, 0);
      grad.addColorStop(0, rgb(TEAL_1, 1));
      grad.addColorStop(1, rgb(TEAL_2, 1));

      ctx!.fillStyle = grad;
      ctx!.beginPath();
      // Paper airplane shape
      ctx!.moveTo(size, 0);
      ctx!.lineTo(-size * 0.6, -size * 0.45);
      ctx!.lineTo(-size * 0.25, 0);
      ctx!.lineTo(-size * 0.6, size * 0.45);
      ctx!.closePath();
      ctx!.fill();

      // Wing fold line
      ctx!.strokeStyle = rgb(BG, 0.3);
      ctx!.lineWidth = 0.5;
      ctx!.beginPath();
      ctx!.moveTo(size * 0.6, 0);
      ctx!.lineTo(-size * 0.25, 0);
      ctx!.stroke();

      ctx!.restore();
    }

    /* ── Draw water drop ── */
    function drawDrop(x: number, y: number, scale: number, alpha: number) {
      ctx!.save();
      ctx!.translate(x, y);
      ctx!.scale(scale, scale);
      ctx!.globalAlpha = alpha;

      // Glow
      const glow = ctx!.createRadialGradient(0, 0, 0, 0, 0, 20);
      glow.addColorStop(0, rgb(TEAL_1, 0.4));
      glow.addColorStop(0.5, rgb(TEAL_2, 0.15));
      glow.addColorStop(1, rgb(TEAL_2, 0));
      ctx!.fillStyle = glow;
      ctx!.beginPath();
      ctx!.arc(0, 0, 20, 0, Math.PI * 2);
      ctx!.fill();

      // Drop shape
      const dropGrad = ctx!.createLinearGradient(0, -8, 0, 8);
      dropGrad.addColorStop(0, rgb(TEAL_1, 1));
      dropGrad.addColorStop(1, rgb(TEAL_2, 1));
      ctx!.fillStyle = dropGrad;
      ctx!.beginPath();
      ctx!.moveTo(0, -10);
      ctx!.bezierCurveTo(-6, -2, -6, 6, 0, 10);
      ctx!.bezierCurveTo(6, 6, 6, -2, 0, -10);
      ctx!.fill();

      ctx!.restore();
    }

    /* ── Main loop ── */
    function frame(now: number) {
      const dt = Math.min((now - prevTime) / 1000, 0.05);
      prevTime = now;
      elapsed += dt;

      ctx!.clearRect(0, 0, w, h);

      // ── Particles ──
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.pulse += p.speed;
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;

        const a = p.alpha * (0.6 + 0.4 * Math.sin(p.pulse));
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = rgb(lerpColor(0.5), a);
        ctx!.fill();
      }

      // ── Plane / drop cycle ──
      if (dropPhase === 0) {
        // Flying phase
        const cycleT = (elapsed % CYCLE) / CYCLE;
        const t = Math.min(cycleT / 0.85, 1); // use 85% of cycle for flight
        const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const pos = bezierPoint(eased);

        // Compute angle from trail
        const nextT = Math.min((eased + 0.01), 1);
        const nextPos = bezierPoint(nextT);
        const angle = Math.atan2(nextPos.y - pos.y, nextPos.x - pos.x);

        // Trail
        trail.push({ x: pos.x, y: pos.y, age: 0 });
        if (trail.length > TRAIL_MAX) trail.shift();

        // Draw trail
        for (let i = 0; i < trail.length; i++) {
          trail[i].age += dt;
          const ta = 1 - i / trail.length;
          const fadeA = Math.max(0, ta * 0.5 * (1 - trail[i].age * 0.8));
          if (fadeA <= 0) continue;
          ctx!.beginPath();
          ctx!.arc(trail[i].x, trail[i].y, 2 * ta + 0.5, 0, Math.PI * 2);
          ctx!.fillStyle = rgb(lerpColor(i / trail.length), fadeA);
          ctx!.fill();
        }

        // Draw plane
        drawPlane(pos.x, pos.y, angle, 14, 0.85);

        // Transition to dive at ~85% of cycle
        if (cycleT >= 0.85) {
          dropPhase = 1;
          dropTimer = 0;
          dropX = pos.x;
          dropY = pos.y;
        }
      } else if (dropPhase === 1) {
        // Diving phase (~0.6s)
        dropTimer += dt;
        const diveDur = 0.6;
        const diveT = Math.min(dropTimer / diveDur, 1);

        // Plane shrinks and dives down
        const x = dropX + diveT * 30;
        const y = dropY + diveT * 60;
        const angle = Math.PI * 0.35 + diveT * 0.3;
        const planeScale = 1 - diveT;
        const dropAppear = diveT;

        // Fade trail
        for (let i = 0; i < trail.length; i++) {
          trail[i].age += dt * 3;
          const ta = 1 - i / trail.length;
          const fadeA = Math.max(0, ta * 0.3 * (1 - trail[i].age * 0.8));
          if (fadeA <= 0) continue;
          ctx!.beginPath();
          ctx!.arc(trail[i].x, trail[i].y, 2 * ta, 0, Math.PI * 2);
          ctx!.fillStyle = rgb(lerpColor(0.5), fadeA);
          ctx!.fill();
        }

        if (planeScale > 0.05) {
          drawPlane(x, y, angle, 14 * planeScale, planeScale * 0.85);
        }
        if (dropAppear > 0.3) {
          drawDrop(x, y, dropAppear, dropAppear * 0.8);
        }

        if (diveT >= 1) {
          dropPhase = 2;
          dropTimer = 0;
          dropX = x;
          dropY = y;
          dropAlpha = 1;
          dropScale = 1;
        }
      } else if (dropPhase === 2) {
        // Glow phase (~0.5s)
        dropTimer += dt;
        const glowDur = 0.5;
        const glowT = Math.min(dropTimer / glowDur, 1);

        dropScale = 1 + glowT * 0.5;
        dropAlpha = 1;
        drawDrop(dropX, dropY, dropScale, dropAlpha);

        if (glowT >= 1) {
          dropPhase = 3;
          dropTimer = 0;
        }
      } else if (dropPhase === 3) {
        // Fade phase (~0.4s)
        dropTimer += dt;
        const fadeDur = 0.4;
        const fadeT = Math.min(dropTimer / fadeDur, 1);

        dropAlpha = 1 - fadeT;
        dropScale = 1.5 + fadeT * 0.3;
        drawDrop(dropX, dropY, dropScale, dropAlpha);

        if (fadeT >= 1) {
          // Reset
          dropPhase = 0;
          trail.length = 0;
          elapsed = 0;
        }
      }

      animId = requestAnimationFrame(frame);
    }

    animId = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  );
}
