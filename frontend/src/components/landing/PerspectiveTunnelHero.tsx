import {
  motion,
  useTransform,
  useReducedMotion,
  useMotionValue,
  useSpring,
  MotionValue,
} from 'framer-motion';
import { useEffect, useRef, useState } from 'react';

/** The AutoImmune pipeline, in order. Each stage is one card in the tunnel. */
const STAGES = [
  { step: '01', title: 'Observe', detail: '/actuator/health + probes' },
  { step: '02', title: 'Detect', detail: 'two failed checks, 5 s apart' },
  { step: '03', title: 'Diagnose', detail: 'LLM or top stack frame' },
  { step: '04', title: 'Draft patches', detail: 'three candidates' },
  { step: 'V0', title: 'Compile', detail: 'git apply --check · mvn compile' },
  { step: 'V1', title: 'Target test', detail: 'visible fault test passes' },
  { step: 'V2', title: 'Full suite', detail: 'existing tests still pass' },
  { step: 'V3', title: 'Semgrep', detail: 'only NEW findings count' },
  { step: '05', title: 'Decide', detail: 'REJECT · ESCALATE · AUTO_APPLY' },
  { step: '06', title: 'Deploy & watch', detail: 'promote or roll back' },
];

type Stage = (typeof STAGES)[number];

interface TunnelCardData {
  item: Stage;
  angleCos: number;
  angleSin: number;
  radiusFactorX: number;
  radiusFactorY: number;
  rotationZ: number;
  index: number;
}

const TUNNEL_CARDS: TunnelCardData[] = STAGES.map((item, i) => {
  const goldenAngle = i * 137.5 * (Math.PI / 180);
  return {
    item,
    angleCos: Math.cos(goldenAngle),
    angleSin: Math.sin(goldenAngle),
    radiusFactorX: 0.28 + (i % 3) * 0.08,
    radiusFactorY: 0.26 + (i % 2) * 0.09,
    rotationZ: (i % 2 === 0 ? 1 : -1) * (3 + (i % 5) * 2),
    index: i,
  };
});

const SPRING_CONFIG = { stiffness: 60, damping: 25, mass: 0.5 };
const HEADER_PX = 56; // sticky site header (h-14)

interface StageDimensions {
  width: number;
  height: number;
  isMobile: boolean;
}

function useCameraParallax(enabled: boolean) {
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const x = useSpring(rawX, SPRING_CONFIG);
  const y = useSpring(rawY, SPRING_CONFIG);

  useEffect(() => {
    if (!enabled) return;
    const onMove = (e: PointerEvent) => {
      rawX.set((e.clientX / window.innerWidth - 0.5) * 2);
      rawY.set((e.clientY / window.innerHeight - 0.5) * 2);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, [enabled, rawX, rawY]);

  return { x, y };
}

interface TunnelCardProps {
  card: TunnelCardData;
  progress: MotionValue<number>;
  pointer: { x: MotionValue<number>; y: MotionValue<number> };
  total: number;
  stage: StageDimensions;
}

function TunnelCard({ card, progress, pointer, total, stage }: TunnelCardProps) {
  const staggerSpan = 0.55;
  const start = (card.index / total) * (1 - staggerSpan);
  const end = start + staggerSpan;

  const localProgress = useTransform(progress, [start, end], [0, 1]);

  const farZ = stage.isMobile ? -1200 : -1700;
  const nearZ = stage.isMobile ? 350 : 500;
  const z = useTransform(localProgress, [0, 1], [farZ, nearZ]);
  const opacity = useTransform(localProgress, [0, 0.18, 0.82, 0.98], [0, 1, 1, 0]);

  const cardWidth = stage.isMobile
    ? Math.max(130, Math.min(180, stage.width * 0.38))
    : Math.max(180, Math.min(250, stage.width * 0.17));

  const baseX = card.angleCos * (stage.width * card.radiusFactorX);
  const baseY = card.angleSin * (stage.height * card.radiusFactorY);
  const panStrength = stage.isMobile ? 20 : 45;

  const transform = useTransform([z, pointer.x, pointer.y], ([currZ, px, py]: number[]) => {
    const offsetX = baseX - px * panStrength;
    const offsetY = baseY - py * panStrength;
    return `translate3d(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px), ${currZ}px) rotateZ(${card.rotationZ}deg)`;
  });

  const isGate = card.item.step.startsWith('V');

  return (
    <motion.div
      // Earlier cards are always nearer the camera, so they must stack on top.
      style={{ width: cardWidth, transform, opacity, zIndex: total - card.index }}
      className="absolute left-1/2 top-1/2 aspect-[4/5] will-change-transform select-none"
      aria-hidden="true"
    >
      <div className="relative h-full w-full overflow-hidden rounded-2xl bg-surface shadow-2 ring-1 ring-line-strong flex flex-col justify-between p-5">
        <span
          className={`font-mono text-4xl sm:text-5xl font-bold tracking-tighter ${
            isGate ? 'text-lead-ink' : 'text-text-3'
          }`}
        >
          {card.item.step}
        </span>
        <div className="flex flex-col gap-1.5">
          <span className="text-base sm:text-lg font-semibold text-text leading-tight">
            {card.item.title}
          </span>
          <span className="text-[11px] sm:text-xs font-mono text-text-2 leading-snug">
            {card.item.detail}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

export default function PerspectiveTunnelHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  const [stage, setStage] = useState<StageDimensions>({ width: 1440, height: 900, isMobile: false });

  useEffect(() => {
    const updateDimensions = () =>
      setStage({
        width: window.innerWidth,
        height: window.innerHeight - HEADER_PX,
        isMobile: window.innerWidth < 768,
      });
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const rawProgress = useMotionValue(0);
  const smoothProgress = useSpring(rawProgress, { stiffness: 80, damping: 30, restDelta: 0.0001 });

  // Wheel / touch drive the tunnel only while the hero is fully in view and the
  // tunnel has room to move in that direction. At either end, the page scrolls
  // normally, so the content below the hero stays reachable.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const advance = (delta: number): boolean => {
      if (window.scrollY > 1) return false;
      const current = rawProgress.get();
      const next = Math.min(1, Math.max(0, current + delta));
      if (next === current) return false;
      rawProgress.set(next);
      return true;
    };

    const onWheel = (e: WheelEvent) => {
      if (advance(e.deltaY * 0.0008)) e.preventDefault();
    };

    let lastY: number | null = null;
    const onTouchStart = (e: TouchEvent) => {
      lastY = e.touches[0]?.clientY ?? null;
    };
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY;
      if (lastY === null || y === undefined) return;
      const delta = (lastY - y) * 0.0025;
      lastY = y;
      if (advance(delta)) e.preventDefault();
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
    };
  }, [rawProgress]);

  const pointer = useCameraParallax(!reduce);

  const titleScale = useTransform(smoothProgress, [0, 0.5, 1], [0.8, 1, 1.1]);
  const titleOpacity = useTransform(smoothProgress, [0, 0.12], [0.35, 1]);
  const startPromptOpacity = useTransform(smoothProgress, [0, 0.12], [1, 0]);
  const endPromptOpacity = useTransform(smoothProgress, [0.85, 1], [0, 1]);

  return (
    <section
      ref={containerRef}
      aria-label="AutoImmune pipeline overview"
      className="relative h-[calc(100svh-3.5rem)] w-full overflow-hidden bg-page text-text select-none flex items-center justify-center border-b border-line"
      style={{ perspective: stage.isMobile ? '900px' : '1200px', transformStyle: 'preserve-3d' }}
    >
      {/* Background grid and glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(var(--line-strong)_1px,transparent_1px)] [background-size:28px_28px] [mask-image:radial-gradient(ellipse_70%_70%_at_50%_50%,#000_60%,transparent_100%)] opacity-60" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,var(--lead-tint)_0%,transparent_70%)]" />

      {/* Depth ring guides */}
      <div className="pointer-events-none absolute h-[48vmin] w-[48vmin] rounded-full border border-lead-line" />
      <div className="pointer-events-none absolute h-[76vmin] w-[76vmin] rounded-full border border-dashed border-line-strong" />

      {/* Central title */}
      <motion.div
        style={{ scale: titleScale, opacity: titleOpacity }}
        className="pointer-events-none z-0 flex flex-col items-center text-center px-6 max-w-xl"
      >
        <p className="text-xs font-mono uppercase tracking-[0.4em] text-lead-ink mb-4">
          Observe → Detect → Repair → Gate → Deploy
        </p>
        <p className="text-5xl sm:text-7xl md:text-8xl font-bold tracking-tighter leading-[0.9] text-text">
          AUTO
          <br />
          IMMUNE.
        </p>
        <p className="mt-4 max-w-[38ch] text-sm sm:text-base text-text-2">
          Scroll to travel through the self-healing pipeline, from detection to a gated deployment.
        </p>
      </motion.div>

      {/* Scroll prompts */}
      <motion.div
        style={{ opacity: startPromptOpacity }}
        className="pointer-events-none absolute bottom-8 z-20 flex flex-col items-center gap-2 text-xs font-mono uppercase tracking-[0.3em] text-text-3"
      >
        <span>Scroll to explore</span>
        <div className="h-6 w-px bg-gradient-to-b from-lead to-transparent" />
      </motion.div>
      <motion.div
        style={{ opacity: endPromptOpacity }}
        className="pointer-events-none absolute bottom-8 z-20 flex flex-col items-center gap-2 text-xs font-mono uppercase tracking-[0.3em] text-text-3"
      >
        <span>Keep scrolling for the study</span>
        <div className="h-6 w-px bg-gradient-to-b from-lead to-transparent" />
      </motion.div>

      {/* 3D z-space plane */}
      <div className="absolute inset-0 pointer-events-none" style={{ transformStyle: 'preserve-3d' }}>
        {TUNNEL_CARDS.map((card) => (
          <TunnelCard
            key={card.item.step}
            card={card}
            progress={smoothProgress}
            pointer={pointer}
            total={TUNNEL_CARDS.length}
            stage={stage}
          />
        ))}
      </div>
    </section>
  );
}
