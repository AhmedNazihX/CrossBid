'use client'

import { useEffect, useRef, useState } from 'react'
import Image from 'next/image'

/**
 * The logo reveal that opens the hero — **not from `Landing.dc.html`**. Added on the user's
 * instruction after the canvas was confirmed (ADR-0014), so it cites no artboard; the ADR
 * records the deviation.
 *
 * The source is `docs/design/canvas/CrossBid Logo Reveal.mp4` — 1920 × 1080, H.264, **14.8 s**,
 * **no audio track** (re-verified on this encode: 0 audio bytes decoded against 72 MB of
 * video), which is what makes an autoplaying `muted` video unobjectionable: there is no
 * sound to suppress and none to restore. Everything else here follows from measuring the
 * file frame by frame through a canvas rather than guessing at it.
 *
 * **The served file is the reveal alone, and it is a derivative.** The canvas master is the
 * full 14.8 s cycle: the mark draws in, the rings then shrink through two passes, and the
 * whole thing reverses back to an empty frame (the plateaus mirror exactly — 47 005 mark px
 * at 2.5–3.25 s against 47 008 at 11.75–12.5 s — so it is built for seamless looping). None
 * of that after the reveal is wanted, and every byte of it was being downloaded and thrown
 * away. `public/logo-reveal.mp4` is therefore cut from the master with
 *
 *     ffmpeg -i "docs/design/canvas/CrossBid Logo Reveal.mp4" -t 4.24 \
 *       -c copy -movflags +faststart frontend/public/logo-reveal.mp4
 *
 * which takes it from **2.43 MB to 0.48 MB, 80 % smaller**, on the page that matters most.
 * Re-run it if the master ever changes.
 *
 * **`-c copy`, not a re-encode, and that is not laziness.** Re-encoding at CRF 18 reached
 * 0.30 MB and was indistinguishable in every still — but measured in the browser the ground
 * came back **231 where the master decodes to 250**. Chrome reads this file as full range
 * whatever the container says (`color_range=pc`, x264 `fullrange=1`, `-vf scale=in_range=…:
 * out_range=…`, and a `tv` tag were each tried; every one still decoded to 231), so an
 * encoder that writes limited-range values shifts the ground permanently. With the
 * `multiply` blend below, a ground of 231 against a 250 canvas paints a visibly darker
 * rectangle across the hero — the exact seam the mask and the brightness lift exist to
 * remove. A stream copy cannot introduce it: the held frame is byte-identical to the
 * master's, same SHA-256.
 *
 * **There is no pause control, and none is required.** WCAG 2.2.2 governs motion that plays
 * automatically for more than five seconds; this window is 2.94 s at natural speed. Earlier
 * cuts of this component ran to 7.56 s, 10.70 s and the full 14.8 s, and each needed either a
 * rate fast enough to read as a fast-forward or a visible control. Stopping where the reveal
 * actually ends removes the dilemma rather than trading one horn for the other.
 *
 * **It is a band, not a box — and it is masked, not clipped.** The mark occupies only
 * x 18.85–81.15 % and y 36.67–63.24 % of the frame; the rest is ground at `#FAFAFA`, within
 * one value of `--surface-canvas`. Rendered whole and framed it read as a large empty card
 * with the mark lost in the middle, so the band is sized to the mark.
 *
 * But the clip's concentric rings run the **full height of the source frame** (measured
 * 0.000–1.000 from 1.5 s to 4.0 s, i.e. the source already clips them at its own edges), so
 * a hard crop sliced them with a straight edge mid-animation. Opening the band to fit them
 * would make it 537 px tall instead of 216 and drop the mark to ~595 px, under the
 * headline's 678 px. Instead the video overflows the band and a radial mask fades it out:
 * the rings dissolve into the canvas rather than ending at a line, the layout box stays the
 * size of the mark, and nothing below it moves. The hero section's own `overflow-hidden`
 * contains the horizontal spill, so no viewport gains a scrollbar.
 *
 */
const REVEAL_SRC = '/logo-reveal.mp4'
const LOCKUP_SRC = '/logo-lockup.svg'

/**
 * The played window, in seconds of source time.
 *
 * **The start** skips dead time only: one unchanging 622 px dot from 0.5 s through 1.26 s,
 * with real motion from 1.28 s.
 *
 * **The hold is where the reveal finishes and before the rings begin to move** — measured at
 * full 1920 × 1080, tracking two things at once. The mark's mean darkness falls 53.2 at 3.4 s,
 * 27.4 at 4.0, 24.5 at 4.1 and reaches its solid plateau of ~20.25 by **4.20 s**. The outer
 * ring's radius holds at **889 px through 4.20 s** and then shrinks continuously — 888 at
 * 4.22, 887 at 4.42, 886 at 4.52, collapsing to 331 by 6.4 s. 4.20 s is the last frame that
 * is both: logo complete, rings untouched.
 *
 * (The half-resolution pass that preceded this read the radius as a flat 445 px from 3.4 s to
 * 4.3 s and suggested 4.3. That plateau was quantisation, not the animation — at full
 * resolution the shrink starts one frame after 4.20.)
 */
const REVEAL_START_SECONDS = 1.26
const REVEAL_HOLD_SECONDS = 4.2

/**
 * Natural speed, which the window is finally short enough to allow.
 *
 * 1.26 s → 4.20 s is 2.94 s of motion, inside WCAG 2.2.2's five seconds with room to spare —
 * so nothing is hurried and no pause control is owed. Every earlier version of this file
 * traded one of those away; this one does not have to. Moving `REVEAL_HOLD_SECONDS` later is
 * what would bring the dilemma back.
 */
const PLAYBACK_RATE = 1.0

/**
 * The slice of the frame that is kept, as fractions of its width and height.
 *
 * Measured on the plateau the hold sits on (sampled at 10.76 s): the mark's own ink runs
 * x 18.85 %–81.15 % and y 36.67 %–63.24 %, so it is 62.30 % of the frame wide and 26.57 %
 * tall — the rest is ground and a few very faint concentric rings. Cropping both axes rather
 * than only the vertical is what lets the mark render large without the band swallowing the
 * fold: inside this window the mark fills 89 % of the width, against 62 % of the raw frame.
 *
 * The bounds keep about 3.9 % of air on each side and 2.7 % above and below, so it does not
 * read as trimmed, and the lower one stays clear of the tagline — which is the `<h1>` word
 * for word. **The window is unchanged from the first encode**: the re-cut lengthened the clip
 * and added the reverse, but moved the mark's geometry by under a tenth of a percent, so
 * nothing below needed re-deriving. (Mid-reveal the mark is fractionally larger — 18.12 %–
 * 81.87 % × 36.39 %–63.52 % at 6.82 s — which the window also clears.)
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

/**
 * The mask that dissolves the overflowing rings.
 *
 * Stops are in the *video's* own box, not the band's: the band occupies its middle 34–66 %
 * vertically (the crop window), so the mask is fully opaque across exactly that span and
 * fades over the 14 % either side — about 95 px at the rendered size, which lands the rings
 * at nothing before they reach the pill or the headline. Horizontally it holds to 80 %,
 * since the frame has more dead margin on the sides than the rings need.
 */
const RING_FADE =
  'radial-gradient(ellipse 80% 66% at 50% 50%, #000 40%, rgba(0,0,0,0.45) 70%, transparent 100%)'

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
     * Switches to the settle rate, then holds on the last whole frame of the mark.
     *
     * Watched with `requestAnimationFrame`, not `timeupdate`: that event fires about four
     * times a second, so on an earlier window the first tick past the hold point measured a
     * quarter-second late, with the mark already dissolving. A frame loop checks every
     * ~16 ms, and the seek afterwards lands the paused frame exactly on the hold point
     * whatever the jitter, so the resting image is identical on every load.
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
     * promise rejects, and a component that had already faded the lockup out would leave an
     * empty band: the start frame carries one dot, which is to say nothing. Hung off the
     * event instead, a refusal simply never fires it, so the lockup stays up and the reveal
     * degrades to the same still a reduced-motion visitor gets.
     */
    const onPlaying = () => {
      setHasStarted(true)
      holdFrameRef.current = requestAnimationFrame(watchForHold)
    }
    video.addEventListener('playing', onPlaying)

    const start = () => {
      video.playbackRate = PLAYBACK_RATE
      video.currentTime = REVEAL_START_SECONDS
      // A refusal needs no handling beyond not throwing: `playing` does not fire, so nothing
      // above runs and the static lockup is what stays on screen.
      void video.play().catch(() => undefined)
    }

    // Seeking before metadata exists is dropped silently, which would start the clip at 0
    // and play the dead opening the start is there to skip.
    const startWhenSeekable = () => {
      if (video.readyState >= HAVE_METADATA) {
        start()
        return
      }
      video.addEventListener('loadedmetadata', start, { once: true })
    }

    // Observes the *band*, not the video. The video is 312 % of the band tall and 143 % wide,
    // so all but 22.4 % of it is clipped away — below this threshold, and the observer would
    // never fire at all. The band is what the visitor actually sees.
    //
    // The hero is above the fold, so this fires at once on a normal visit; it earns its keep
    // when someone lands deep in the page on an anchor and scrolls back up.
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
      ref={bandRef}
      // Decorative: the brand name is already text in the nav, and the tagline the clip
      // builds towards is the `<h1>` immediately below. Nothing here is information of its
      // own, and there is no control to keep reachable.
      aria-hidden="true"
      className="relative mx-auto mb-8 w-full"
      style={{ aspectRatio: BAND_ASPECT, maxWidth: BAND_MAX_WIDTH }}
    >
      {/* Poster and fallback both. It must fade out once the clip starts: `multiply` makes
          the video's ground transparent, so anything left underneath shows straight through
          the mark — two offset lockups at once. */}
      <Image
        src={LOCKUP_SRC}
        alt=""
        fill
        sizes="840px"
        priority
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
            // Fades the overflow instead of cutting it. Opaque across the mark, then out
            // to nothing well before the pill above and the headline below — so the rings
            // read as dissolving into the page rather than as a cropped rectangle.
            maskImage: RING_FADE,
            WebkitMaskImage: RING_FADE,
          }}
          className={`absolute max-w-none transition-opacity duration-300 ${
            hasStarted ? 'opacity-100' : 'opacity-0'
          }`}
        />
      )}
    </div>
  )
}
