# Brand conformance

**DOC NO. RL-Z0-A · REV. A**

Channel Z0 is a Riposte Laboratories transmission and follows the
[Riposte design system](https://github.com/armeehn/riposte-brand) —
published at [ripostelabs.xyz/brand](https://ripostelabs.xyz/brand/) — with one large,
deliberate exception documented below.

---

## Conforms

| Surface | Status |
|---|---|
| README | Already spec-sheet shaped: the `CH 0 · DESIG RL-Z0` titleblock is the document-chrome register done correctly |
| Doc control | `DESIG RL-Z0` predates this guide and is retained as the canonical designation |
| Voice | Concrete, deadpan, wit from precision. "A local channel, for locals" is the register exactly |
| `docs/*.md` | Tables over prose, sentence-case headings, numbers bolded |
| Monospace throughout | `--mono` variable, no proportional face in the chrome |

## Deliberately diverges — the CRT exception

**`site/retro/` and the playout bumpers use a broadcast-phosphor palette, not the Riposte
palette.** Amber `#ffb000`, phosphor red `#ff2d2d`, near-black `#0d0d0d`/`#141414`/`#1f1f1f`,
and Courier New rather than JetBrains Mono.

This is correct and should not be "fixed". Channel Z0 is a simulation of an analogue local
TV channel; the whole premise is that it looks like something transmitted in 1987. The
Riposte brand is a *printed engineering document* — applying bone paper and harlequin bands
to a CRT sign-off card would destroy the conceit that makes the project work.

The rule of thumb: **anything that represents the broadcast gets the phosphor treatment;
anything that represents Riposte operating the broadcast gets the brand.**

| Surface | Palette |
|---|---|
| `site/retro/`, bumpers, sign-off, on-air graphics | Phosphor. Courier. CRT. |
| `site/index.html` (the public-facing station page) | **Riposte brand** — queued below |
| `docs/`, README, schedules, ad standards | Riposte brand |

## Queued

- [ ] Bring `site/index.html` onto `riposte-brand.css`. It is the station's front door — the
      page a submitter or advertiser lands on — so it should read as a Riposte property that
      happens to run a retro channel, with the phosphor aesthetic quarantined behind
      `/retro/`. Currently it uses a neutral dark palette (`#1f1f1f`, `#141414`, `#b9b4a6`)
      that is neither.
- [ ] Add the standard `footer.colophon` to `site/index.html`, linking `/brand/`.
- [ ] `docs/ad-standards.md` should carry `SEC.NN` numbering — it is a specification and
      would read better filed as one.

## Quick reference

```
ink      #1d1a17      pink     #f0477d   (bone text; display only, 3.16:1)
bone     #f6f1e7      marigold #fe9a0d   (INK text; 8.12:1, safe for prose)
bone-dim #eae4d6      teal     #12b795   (bone text; fills only, 2.27:1)

deep, for accent fills that carry a sentence:
pink-deep #d81150   marigold-deep #a15e01   teal-deep #0c7a63

font     JetBrains Mono 400 / 700 / 800
spacing  4 8 12 16 24 34 48 64 72     radius 0     rules 2px solid / 1px dashed
```

Full guide: <https://github.com/armeehn/riposte-brand>

---

<table>
<tr>
<td><b>DOC NO. RL-Z0-A</b><br>REV. A · EST. 2026</td>
<td align="right"><b>PARRY ♻ RIPOSTE ♻ RECYCLE ♻ REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
