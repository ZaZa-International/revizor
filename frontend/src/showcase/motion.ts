import { useEffect, useRef, useState } from 'react';

export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/* IntersectionObserver-reveal: добавляет .in-view при появлении.
   Работает без GSAP; CSS уважает prefers-reduced-motion. */
export function useReveal<T extends HTMLElement>(threshold = 0.18) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      el.classList.add('in-view');
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('in-view');
            io.unobserve(e.target);
          }
        });
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return ref;
}

/* Монтирует тяжёлых детей только рядом с видимой областью. */
export function useNearViewport<T extends HTMLElement>(rootMargin = '400px'): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        const isNear = entries[0]?.isIntersecting ?? false;
        setNear((prev) => (prev === isNear ? prev : isNear));
      },
      { rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin]);
  return [ref, near];
}