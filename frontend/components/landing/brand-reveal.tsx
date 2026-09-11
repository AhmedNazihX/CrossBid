'use client'

import { useEffect, useRef, useState } from 'react'
import Image from 'next/image'

/**
 * The logo reveal that opens the hero — **not from `Landing.dc.html`**. Added on the user's
 * instruction after the canvas was confirmed (ADR-0014), so it cites no artboard; the ADR
 * records the deviation.
 *
 * The source is `docs/design/canvas/CrossBid Logo Reveal.mp4` — 1920 × 1080, H.264, 8.0 s,
 * **no audio track**, which is what makes an autoplaying `muted` video unobjectionable:
 * there is no sound to suppress and none to restore. Everything else here follows from
 * measuring the file frame by frame through a canvas rather than guessing at it.
 *
 * **It is a band, not a box.** The mark occupies only x 18.80–81.15 % and y 36.67–63.15 %
 * of the frame; the rest is ground at `#FAFAFA`, within one value of `--surface-canvas`.
 * Rendered whole and framed, it read as a large empty card with the mark lost in the
 * middle. Cropped to the mark and dropped straight onto the canvas it reads as part of the
 * page, which is what "seamless" costs: no border, no card, no radius, no backdrop.
 *
 * **It stops on the finished mark, not on the file's last frame.** The reveal fades back to
 * an empty frame over its last fifth of a second — 5.98 % ink at 7.80 s, **0.00 % at
 * 7.90** — so running to 8.00 s would leave a blank strip on the page, the state it rests
 * in for far longer than it plays.
 *
 * **There is no pause control, and none is required.** WCAG 2.2.2 governs motion that plays
 * automatically for *more than five seconds*. The window below runs 3.4 s, so the
 * obligation does not arise and the hero stays clean. That is why the window is where it
 * is: widening it past five seconds silently reintroduces the requirement for a visible
 * pause control, so it cannot be widened without adding one back.
 */
const REVEAL_SRC = '/logo-reveal.mp4'
const LOCKUP_SRC = '/logo-lockup.svg'

/**
 * The played window, in seconds of source time.
 *
 * Measured on the shipped encode, counting non-white pixels across the full 1920 x 1080
 * frame: 652 at 0.8 s and still 652 at 1.2 s — a single dot, dead time nobody should wait
 * through; 47 232 by 2.4 s as the mark builds; 122 885 at 3.8 s once the wordmark is in;
 * 123 632 at 4.0 s and 123 970 at 4.6 s, which is to say flat. The tagline below the mark
 * arrives later still, and repeats the `<h1>` word for word — one more reason the crop
 * ends above it.
 *
 * So: skip the blank opening, hold once the mark is drawn. 3.4 s of motion, under the
 * five-second line of WCAG 2.2.2.
 */
const REVEAL_START_SECONDS = 1.2
const REVEAL_HOLD_SECONDS = 4.6

/**
 * The slice of the frame that is kept, as fractions of its width and height.
 *
 * Measured on the held frame: the mark's own ink runs x 18.80 %–81.15 % and y 36.67 %–
 * 63.15 %, so it is 62.34 % of the frame wide and 26.48 % tall — the rest is ground and a
 * few very faint concentric rings. Cropping both axes rather than only the vertical is what
 * lets the mark render large without the band swallowing the fold: inside this window the
 * mark fills 89 % of the width, against 62 % of the raw frame.
 *
 * The bounds keep roughly 3 % of air on every side so it does not read as trimmed, and the
 * lower one stays clear of the tagline — which is the `<h1>` word for word.
 */
const CROP_LEFT = 0.15
const CROP_RIGHT = 0.85
const CROP_TOP = 0.34
const CROP_BOTTOM = 0.66

const CROP_WIDTH = CROP_RIGHT - CROP_LEFT
const CROP_HEIGHT = CROP_BOTTOM - CROP_TOP

/**
 * How wide the band is allowed to get. At this width the mark lands near 748 px against the
 * headline's widest line at 678 px — a little larger, which is the point of it.
 */
const BAND_MAX_WIDTH = 840

/** 16 : 9 reduced to the kept window, so the band's own box has the right shape. */
const BAND_ASPECT = `${(16 * CROP_WIDTH).toFixed(3)} / ${(9 * CROP_HEIGHT).toFixed(3)}`
/**
 * The video is this much larger than the band, and pulled back by the part cropped off.
 * Both axes are given explicitly rather than leaving one to `auto`: the two agree with
 * 16 : 9 by construction (each is `100 / crop`), so nothing is stretched.
 */
const VIDEO_WIDTH = `${(100 / CROP_WIDTH).toFixed(3)}%`
const VIDEO_HEIGHT = `${(100 / CROP_HEIGHT).toFixed(3)}%`
const VIDEO_LEFT = `${(-100 * (CROP_LEFT / CROP_WIDTH)).toFixed(3)}%`
const VIDEO_TOP = `${(-100 * (CROP_TOP / CROP_HEIGHT)).toFixed(3)}%`

/**
 * The lift that turns the clip's ground into true white, so `multiply` leaves the canvas
 * underneath untouched. Measured: the ground is 250/255, and 255 / 250 = 1.02.
 */
const GROUND_TO_WHITE = 255 / 250

/** `HTMLMediaElement.HAVE_METADATA`, named so the `readyState` check reads as English. */
const HAVE_METADATA = 1
/** Start once a quarter of the band is on screen. */
const PLAY_THRESHOLD = 0.25

/**
 * `true`, `false`, or `null` while still unknown — the third state is the point.
 *
 * The server has no media query to read, so the first paint cannot know the preference.
 * Defaulting to `false` renders the `<video>` for one tick, and `preload="metadata"` is
 * enough to put a request for the clip on the wire before the effect can remove it again
 * (measured: one request even with the element gone by the time anything is visible).
 * Holding `null` until mount means a visitor who asked for reduced motion fetches nothing
 * at all, and costs nothing the other way: the video is transparent until it plays.
 */
function usePrefersReducedMotion(): boolean | null {
  const [prefersReduced, setPrefersReduced] = useState<boolean | null>(null)

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    setPrefersReduced(query.matches)

    const onChange = (event: MediaQueryListEvent) => setPrefersReduced(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return prefersReduced
}

export function BrandReveal() {
  const bandRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const holdFrameRef = useRef<number | null>(null)
  const [hasStarted, setHasStarted] = useState(false)
  const prefersReducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    const video = videoRef.current
    const band = bandRef.current
    if (prefersReducedMotion !== false || video === null || band === null) return

    /**
     * Hold on the last drawn frame.
     *
     * Watched with `requestAnimationFrame`, not the `timeupdate` event: `timeupdate` fires
     * about four times a second, so on the earlier full-length window the first tick past
     * the hold point measured 7.93 s — a quarter-second late, with the mark already
     * dissolving. A frame loop checks every ~16 ms, and the seek afterwards lands the
     * paused frame exactly on the hold point whatever the jitter.
     */
    const watchForHold = () => {
      if (video.currentTime >= REVEAL_HOLD_SECONDS) {
        video.pause()
        video.currentTime = REVEAL_HOLD_SECONDS
        return
      }
      holdFrameRef.current = requestAnimationFrame(watchForHold)
    }

    /**
     * Both the cross-fade and the hold loop hang off `playing`, never off the call.
     *
     * Flipping them when `play()` is *called* is wrong in the one case that matters — iOS
     * Low Power Mode, `media.autoplay.default=5`, any "never autoplay" setting. There the
     * promise rejects, and a component that had already faded the lockup out would leave
     * an empty band: the start frame carries 17 px of ink, which is to say nothing. Hung
     * off the event instead, a refusal simply never fires it, so the lockup stays up and
     * the reveal degrades to the same still a reduced-motion visitor gets.
     *
     * It also keeps the frame loop honest. Started at call time, a refused `play()` left
     * `currentTime` at the window's start forever and `watchForHold` recursing at 60 fps
     * for the life of the page, waiting for a hold point that could never arrive.
     */
    const onPlaying = () => {
      setHasStarted(true)
      holdFrameRef.current = requestAnimationFrame(watchForHold)
    }
    video.addEventListener('playing', onPlaying)

    const start = () => {
      video.currentTime = REVEAL_START_SECONDS
      // A refusal needs no handling beyond not throwing: `playing` does not fire, so
      // nothing above runs and the static lockup is what stays on screen.
      void video.play().catch(() => undefined)
    }

    // Seeking before metadata exists is dropped silently, which would start the clip at 0
    // and play the blank opening the window is there to skip.
    const startWhenSeekable = () => {
      if (video.readyState >= HAVE_METADATA) {
        start()
        return
      }
      video.addEventListener('loadedmetadata', start, { once: true })
    }

    // Observes the *band*, not the video. The video is 312 % of the band tall and 143 %
    // wide, so all but 22.4 % of it is clipped away — below this threshold, and the
    // observer would never fire at all. The band is what the visitor actually sees.
    //
    // The hero is above the fold, so this fires at once on a normal visit; it earns its
    // keep when someone lands deep in the page on an anchor and scrolls back up.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry === undefined || !entry.isIntersecting) return
        observer.disconnect()
        startWhenSeekable()
      },
      { threshold: PLAY_THRESHOLD }
    )
    observer.observe(band)

    return () => {
      observer.disconnect()
      video.removeEventListener('loadedmetadata', start)
      video.removeEventListener('playing', onPlaying)
      if (holdFrameRef.current !== null) cancelAnimationFrame(holdFrameRef.current)
    }
  }, [prefersReducedMotion])

  return (
    <div
      // Decorative: the brand name is already text in the nav, and the tagline the clip
      // builds towards is the `<h1>` immediately below. Nothing here is information of
      // its own, so there is nothing for a screen reader to miss.
      ref={bandRef}
      aria-hidden="true"
      className="relative mx-auto mb-8 w-full overflow-hidden"
      style={{ aspectRatio: BAND_ASPECT, maxWidth: BAND_MAX_WIDTH }}
    >
      {/* Poster and fallback both. It must fade out once the clip starts: `multiply`
          makes the video's ground transparent, so anything left underneath shows straight
          through the mark — two offset lockups at once. */}
      <Image
        src={LOCKUP_SRC}
        alt=""
        fill
        sizes="840px"
        priority
        // The side padding matches the air the crop leaves around the moving mark, so
        // the fallback lands at the same size rather than jumping when one replaces
        // the other.
        className={`object-contain px-[5.5%] transition-opacity duration-300 ${
          hasStarted ? 'opacity-0' : 'opacity-100'
        }`}
      />
      {prefersReducedMotion === false && (
        <video
          ref={videoRef}
          src={REVEAL_SRC}
          muted
          playsInline
          preload="metadata"
          style={{
            width: VIDEO_WIDTH,
            height: VIDEO_HEIGHT,
            left: VIDEO_LEFT,
            top: VIDEO_TOP,
            // The clip's ground is opaque #FAFAFA, so left alone it punches a rectangle
            // through the hero's grid pattern — the exact seam this is meant not to have.
            // `multiply` takes white to transparent, letting the grid run under the mark.
            //
            // The brightness lift is what makes it *exact*. Multiply is a product, so a
            // ground of 250 over a 250 canvas lands on 250 x 250 / 255 = 245: measured as
            // a visible 4-value step at the band's edge. 255 / 250 = 1.02 lifts the ground
            // to true white first, where multiply is the identity and the seam is gone.
            // The mark's own ink brightens by the same 2 %, which is below perception.
            filter: `brightness(${GROUND_TO_WHITE})`,
            mixBlendMode: 'multiply',
          }}
          className={`absolute max-w-none transition-opacity duration-300 ${
            hasStarted ? 'opacity-100' : 'opacity-0'
          }`}
        />
      )}
    </div>
  )
}
