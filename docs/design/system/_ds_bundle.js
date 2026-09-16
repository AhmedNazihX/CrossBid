/* @ds-bundle: {"format":4,"namespace":"CrossBidDesignSystem_b81312","components":[{"name":"MetricCard","sourcePath":"components/app/MetricCard.jsx"},{"name":"NavItem","sourcePath":"components/app/NavItem.jsx"},{"name":"RunCard","sourcePath":"components/app/RunCard.jsx"},{"name":"VerdictChip","sourcePath":"components/app/VerdictChip.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Tabs","sourcePath":"components/core/Tabs.jsx"},{"name":"Tag","sourcePath":"components/core/Tag.jsx"},{"name":"Tooltip","sourcePath":"components/core/Tooltip.jsx"},{"name":"Dialog","sourcePath":"components/feedback/Dialog.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Radio","sourcePath":"components/forms/Radio.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"}],"sourceHashes":{"components/app/MetricCard.jsx":"05a51f53dfe7","components/app/NavItem.jsx":"0b154ab45d0e","components/app/RunCard.jsx":"45e9d9fdfabc","components/app/VerdictChip.jsx":"03d17b1f9a64","components/core/Badge.jsx":"09a8b4576f9e","components/core/Button.jsx":"a9dd99e5a548","components/core/Card.jsx":"fa4ee17008d6","components/core/IconButton.jsx":"7803fe5cd03c","components/core/Tabs.jsx":"2de182e7357d","components/core/Tag.jsx":"c1daa77076e9","components/core/Tooltip.jsx":"609c57f52932","components/feedback/Dialog.jsx":"c3044008750e","components/feedback/Toast.jsx":"b65050b05547","components/forms/Checkbox.jsx":"f152ce46ecf9","components/forms/Input.jsx":"a0cbafa6c0c0","components/forms/Radio.jsx":"6f70bc4b3b1f","components/forms/Select.jsx":"9ebe4b75e91e","components/forms/Switch.jsx":"32c651b9dc2e","ui_kits/app/Dashboard.jsx":"f055cddcfe46","ui_kits/app/Icons.jsx":"ebc373f44609","ui_kits/app/Matrix.jsx":"e3d4de9161f5","ui_kits/app/Runs.jsx":"b0d9d41d3b7d","ui_kits/app/Shell.jsx":"2dc0fd08166e","ui_kits/app/Verdict.jsx":"aeb1a6fcebda","ui_kits/app/data.js":"8204922831d4","ui_kits/loader.js":"f3e15323da2d","ui_kits/website/Footer.jsx":"d8929d387cc2","ui_kits/website/Hero.jsx":"8bc95e7dd5a8","ui_kits/website/Nav.jsx":"fa4cc20013db","ui_kits/website/Sections.jsx":"070a899c6b55"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.CrossBidDesignSystem_b81312 = window.CrossBidDesignSystem_b81312 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/app/MetricCard.jsx
try { (() => {
function MetricCard({
  label,
  value,
  delta,
  deltaTone = 'success',
  period,
  style
}) {
  const c = deltaTone === 'success' ? 'var(--status-success-text)' : deltaTone === 'danger' ? 'var(--status-danger-text)' : 'var(--text-muted)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      padding: 24,
      boxShadow: 'var(--shadow-xs)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-body)',
      color: 'var(--text-secondary)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '600 32px/1.1 var(--font-sans)',
      letterSpacing: 'var(--tracking-tight)',
      marginTop: 8
    }
  }, value), (delta || period) && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      font: 'var(--type-body-sm)',
      marginTop: 10
    }
  }, delta && /*#__PURE__*/React.createElement("span", {
    style: {
      color: c,
      fontWeight: 500
    }
  }, delta), period && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, period)));
}
Object.assign(__ds_scope, { MetricCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/MetricCard.jsx", error: String((e && e.message) || e) }); }

// components/app/NavItem.jsx
try { (() => {
function NavItem({
  icon,
  label,
  active,
  tone = 'soft',
  trailing,
  onClick
}) {
  const [hov, setHov] = React.useState(false);
  const solid = tone === 'solid';
  return /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    onMouseEnter: () => setHov(true),
    onMouseLeave: () => setHov(false),
    style: {
      all: 'unset',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      width: '100%',
      boxSizing: 'border-box',
      height: 44,
      padding: '0 10px',
      borderRadius: 'var(--radius-md)',
      cursor: 'pointer',
      background: active ? 'var(--surface-card)' : hov ? 'var(--surface-hover)' : 'transparent',
      border: `1px solid ${active ? 'var(--border-default)' : 'transparent'}`,
      boxShadow: active ? 'var(--shadow-active-nav)' : 'none',
      transition: 'background var(--duration-fast)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 32,
      height: 32,
      borderRadius: 10,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: solid ? 'var(--surface-accent)' : 'var(--cb-blue-100)',
      color: solid ? '#fff' : 'var(--cb-blue-500)',
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 18,
      height: 18
    }
  }, icon)), /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--weight-medium) 15px/1 var(--font-sans)',
      color: 'var(--text-primary)',
      flex: 1
    }
  }, label), trailing && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      display: 'inline-flex'
    }
  }, trailing));
}
Object.assign(__ds_scope, { NavItem });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/NavItem.jsx", error: String((e && e.message) || e) }); }

// components/app/VerdictChip.jsx
try { (() => {
const M = {
  go: ['Go', '--verdict-go'],
  nogo: ['No-go', '--verdict-nogo'],
  conditional: ['Conditional', '--verdict-conditional'],
  insufficient: ['Insufficient evidence', '--verdict-insufficient']
};
function VerdictChip({
  verdict = 'insufficient',
  size = 'md',
  confirmed,
  style
}) {
  const [l, v] = M[verdict] || M.insufficient;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      padding: size === 'lg' ? '10px 14px' : size === 'sm' ? '4px 8px' : '7px 12px',
      borderRadius: 'var(--radius-md)',
      background: `var(${v}-bg)`,
      color: `var(${v}-text)`,
      font: `600 ${size === 'lg' ? 16 : size === 'sm' ? 12 : 14}px/1 var(--font-sans)`,
      whiteSpace: 'nowrap',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: `var(${v})`
    }
  }), l, confirmed && /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 400,
      opacity: .8
    }
  }, "\xB7 confirmed"));
}
Object.assign(__ds_scope, { VerdictChip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/VerdictChip.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
const T = {
  success: ['--status-success', '--status-success-bg', '--status-success-text'],
  warning: ['--status-warning', '--status-warning-bg', '--status-warning-text'],
  danger: ['--status-danger', '--status-danger-bg', '--status-danger-text'],
  info: ['--status-info', '--status-info-bg', '--status-info-text'],
  neutral: ['--status-neutral', '--status-neutral-bg', '--status-neutral-text'],
  brand: ['--cb-blue-500', '--cb-blue-50', '--cb-blue-700']
};
function Badge({
  tone = 'neutral',
  dot = true,
  icon,
  size = 'md',
  pill = true,
  children,
  style
}) {
  const [d, bg, fg] = T[tone] || T.neutral;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: size === 'sm' ? '3px 8px' : '5px 10px',
      borderRadius: pill ? 'var(--radius-pill)' : 'var(--radius-sm)',
      background: `var(${bg})`,
      color: `var(${fg})`,
      font: `var(--weight-medium) ${size === 'sm' ? 11 : 12}px/1.2 var(--font-sans)`,
      whiteSpace: 'nowrap',
      ...style
    }
  }, icon ? /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 14,
      height: 14
    }
  }, icon) : dot && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: '50%',
      background: `var(${d})`,
      flex: 'none'
    }
  }), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const V = {
  primary: {
    bg: 'var(--surface-brand)',
    hover: 'var(--cb-blue-600)',
    color: 'var(--text-inverse)',
    border: 'transparent'
  },
  secondary: {
    bg: 'var(--surface-card)',
    hover: 'var(--surface-hover)',
    color: 'var(--text-primary)',
    border: 'var(--border-default)'
  },
  ghost: {
    bg: 'transparent',
    hover: 'var(--surface-hover)',
    color: 'var(--text-primary)',
    border: 'transparent'
  },
  inverse: {
    bg: 'var(--surface-inverse)',
    hover: 'var(--cb-stone-800)',
    color: 'var(--text-inverse)',
    border: 'transparent'
  },
  danger: {
    bg: 'var(--status-danger)',
    hover: 'var(--status-danger-text)',
    color: 'var(--text-inverse)',
    border: 'transparent'
  }
};
const S = {
  sm: {
    h: 'var(--control-sm)',
    px: 12,
    fs: 13,
    gap: 6
  },
  md: {
    h: 'var(--control-md)',
    px: 16,
    fs: 14,
    gap: 8
  },
  lg: {
    h: 'var(--control-lg)',
    px: 20,
    fs: 15,
    gap: 8
  }
};
function Button({
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  children,
  disabled,
  fullWidth,
  style,
  ...rest
}) {
  const [hov, setHov] = React.useState(false);
  const v = V[variant] || V.primary,
    s = S[size] || S.md;
  return /*#__PURE__*/React.createElement("button", _extends({
    disabled: disabled,
    onMouseEnter: () => setHov(true),
    onMouseLeave: () => setHov(false),
    style: {
      display: fullWidth ? 'flex' : 'inline-flex',
      width: fullWidth ? '100%' : undefined,
      alignItems: 'center',
      justifyContent: 'center',
      gap: s.gap,
      height: s.h,
      padding: `0 ${s.px}px`,
      borderRadius: 'var(--radius-md)',
      border: `1px solid ${v.border}`,
      background: hov && !disabled ? v.hover : v.bg,
      color: v.color,
      font: `var(--weight-medium) ${s.fs}px/1 var(--font-sans)`,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? .5 : 1,
      transition: 'background var(--duration-fast) var(--ease-standard)',
      boxShadow: variant === 'secondary' ? 'var(--shadow-xs)' : 'none',
      whiteSpace: 'nowrap',
      ...style
    }
  }, rest), icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 16,
      height: 16
    }
  }, icon), children, iconRight && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 16,
      height: 16
    }
  }, iconRight));
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/app/RunCard.jsx
try { (() => {
function RunCard({
  title,
  summary,
  status = 'success',
  statusLabel,
  meta = [],
  actionLabel = 'View run',
  onAction,
  style
}) {
  const labels = {
    success: 'Succeeded',
    warning: 'Needs attention',
    danger: 'Failed',
    info: 'In progress',
    neutral: 'Queued'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      padding: 24,
      boxShadow: 'var(--shadow-xs)',
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-h4)',
      letterSpacing: 'var(--tracking-tight)',
      flex: 1
    }
  }, title), /*#__PURE__*/React.createElement(__ds_scope.Button, {
    variant: "secondary",
    size: "sm",
    onClick: onAction,
    icon: /*#__PURE__*/React.createElement("svg", {
      width: "16",
      height: "16",
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "2",
      strokeLinecap: "round",
      strokeLinejoin: "round"
    }, /*#__PURE__*/React.createElement("path", {
      d: "M15 3h6v6"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M10 14 21 3"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"
    }))
  }, actionLabel)), summary && /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-body)',
      color: 'var(--text-secondary)',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, summary), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 20,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: status
  }, statusLabel || labels[status]), meta.map((m, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      font: 'var(--type-body)',
      color: 'var(--text-secondary)'
    }
  }, m.icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 16,
      height: 16,
      color: 'var(--text-muted)'
    }
  }, m.icon), m.label))));
}
Object.assign(__ds_scope, { RunCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/app/RunCard.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function Card({
  title,
  icon,
  actions,
  padding = 24,
  children,
  hoverable,
  style,
  onClick
}) {
  const [hov, setHov] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClick,
    onMouseEnter: () => setHov(true),
    onMouseLeave: () => setHov(false),
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: hoverable && hov ? 'var(--shadow-sm)' : 'var(--shadow-xs)',
      padding,
      cursor: onClick ? 'pointer' : undefined,
      transition: 'box-shadow var(--duration-fast)',
      ...style
    }
  }, (title || actions) && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginBottom: children ? 16 : 0
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 20,
      height: 20,
      color: 'var(--text-primary)'
    }
  }, icon), title && /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-h4)',
      letterSpacing: 'var(--tracking-tight)',
      flex: 1
    }
  }, title), actions && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      alignItems: 'center'
    }
  }, actions)), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function IconButton({
  variant = 'secondary',
  size = 'md',
  label,
  children,
  disabled,
  active,
  style,
  ...rest
}) {
  const [hov, setHov] = React.useState(false);
  const d = size === 'sm' ? 32 : size === 'lg' ? 48 : 40;
  const bg = active ? 'var(--surface-brand-soft)' : hov && !disabled ? 'var(--surface-hover)' : variant === 'ghost' ? 'transparent' : 'var(--surface-card)';
  return /*#__PURE__*/React.createElement("button", _extends({
    "aria-label": label,
    title: label,
    disabled: disabled,
    onMouseEnter: () => setHov(true),
    onMouseLeave: () => setHov(false),
    style: {
      width: d,
      height: d,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 'var(--radius-md)',
      border: variant === 'ghost' ? '1px solid transparent' : '1px solid var(--border-default)',
      background: bg,
      color: active ? 'var(--text-brand)' : 'var(--text-primary)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? .5 : 1,
      transition: 'background var(--duration-fast)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: size === 'sm' ? 16 : 18,
      height: size === 'sm' ? 16 : 18
    }
  }, children));
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Tabs.jsx
try { (() => {
function Tabs({
  items,
  value,
  onChange,
  variant = 'segmented',
  style
}) {
  const [v, setV] = React.useState(value ?? items[0]?.value);
  const cur = value ?? v;
  const set = x => {
    setV(x);
    onChange && onChange(x);
  };
  if (variant === 'underline') return /*#__PURE__*/React.createElement("div", {
    role: "tablist",
    style: {
      display: 'flex',
      gap: 24,
      borderBottom: '1px solid var(--border-default)',
      ...style
    }
  }, items.map(it => /*#__PURE__*/React.createElement("button", {
    key: it.value,
    role: "tab",
    onClick: () => set(it.value),
    style: {
      all: 'unset',
      cursor: 'pointer',
      padding: '10px 0',
      marginBottom: -1,
      font: 'var(--weight-medium) 14px/1 var(--font-sans)',
      color: cur === it.value ? 'var(--text-primary)' : 'var(--text-muted)',
      borderBottom: `2px solid ${cur === it.value ? 'var(--cb-blue-500)' : 'transparent'}`
    }
  }, it.label, it.count != null && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 6,
      color: 'var(--text-muted)',
      fontWeight: 400
    }
  }, it.count))));
  return /*#__PURE__*/React.createElement("div", {
    role: "tablist",
    style: {
      display: 'inline-flex',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      background: 'var(--surface-card)',
      overflow: 'hidden',
      ...style
    }
  }, items.map(it => /*#__PURE__*/React.createElement("button", {
    key: it.value,
    role: "tab",
    onClick: () => set(it.value),
    style: {
      all: 'unset',
      cursor: 'pointer',
      height: 38,
      padding: '0 18px',
      font: 'var(--weight-medium) 14px/1 var(--font-sans)',
      background: cur === it.value ? 'var(--surface-brand)' : 'transparent',
      color: cur === it.value ? '#fff' : 'var(--text-primary)',
      transition: 'background var(--duration-fast)'
    }
  }, it.label)));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/core/Tag.jsx
try { (() => {
function Tag({
  children,
  onRemove,
  mono,
  style
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 8px',
      borderRadius: 'var(--radius-sm)',
      border: '1px solid var(--border-default)',
      background: 'var(--surface-sunken)',
      color: 'var(--text-secondary)',
      font: mono ? 'var(--type-mono)' : 'var(--weight-medium) 12px/1.2 var(--font-sans)',
      ...style
    }
  }, children, onRemove && /*#__PURE__*/React.createElement("button", {
    onClick: onRemove,
    "aria-label": "Remove",
    style: {
      all: 'unset',
      cursor: 'pointer',
      lineHeight: 1,
      color: 'var(--text-muted)',
      fontSize: 13
    }
  }, "\xD7"));
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tag.jsx", error: String((e && e.message) || e) }); }

// components/core/Tooltip.jsx
try { (() => {
function Tooltip({
  content,
  children,
  side = 'top'
}) {
  const [open, setOpen] = React.useState(false);
  const pos = side === 'bottom' ? {
    top: 'calc(100% + 6px)'
  } : {
    bottom: 'calc(100% + 6px)'
  };
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'relative',
      display: 'inline-flex'
    },
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false)
  }, children, open && /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    style: {
      position: 'absolute',
      left: '50%',
      transform: 'translateX(-50%)',
      ...pos,
      zIndex: 50,
      background: 'var(--surface-inverse)',
      color: '#fff',
      padding: '6px 10px',
      borderRadius: 'var(--radius-sm)',
      font: 'var(--weight-medium) 12px/1.3 var(--font-sans)',
      whiteSpace: 'nowrap',
      boxShadow: 'var(--shadow-md)'
    }
  }, content));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Dialog.jsx
try { (() => {
function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = 480
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      position: 'fixed',
      inset: 0,
      background: 'var(--overlay-scrim)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      padding: 24
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    onClick: e => e.stopPropagation(),
    style: {
      width: '100%',
      maxWidth: width,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-lg)',
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-h4)',
      letterSpacing: 'var(--tracking-tight)'
    }
  }, title), description && /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-body)',
      color: 'var(--text-secondary)',
      marginTop: 6
    }
  }, description)), /*#__PURE__*/React.createElement("button", {
    onClick: onClose,
    "aria-label": "Close",
    style: {
      all: 'unset',
      cursor: 'pointer',
      width: 28,
      height: 28,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 6,
      color: 'var(--text-muted)',
      fontSize: 18,
      lineHeight: 1
    }
  }, "\xD7")), children, footer && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'flex-end',
      gap: 8,
      paddingTop: 8
    }
  }, footer)));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
const T = {
  success: '--status-success',
  warning: '--status-warning',
  danger: '--status-danger',
  info: '--status-info'
};
function Toast({
  tone = 'info',
  title,
  description,
  action,
  onDismiss,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    role: "status",
    style: {
      display: 'flex',
      gap: 12,
      alignItems: 'flex-start',
      width: 360,
      padding: '12px 14px',
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-md)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: `var(${T[tone] || T.info})`,
      marginTop: 6,
      flex: 'none'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--weight-medium) 14px/1.3 var(--font-sans)'
    }
  }, title), description && /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'var(--type-body-sm)',
      color: 'var(--text-secondary)',
      marginTop: 2
    }
  }, description), action && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 8
    }
  }, action)), onDismiss && /*#__PURE__*/React.createElement("button", {
    onClick: onDismiss,
    "aria-label": "Dismiss",
    style: {
      all: 'unset',
      cursor: 'pointer',
      color: 'var(--text-muted)',
      fontSize: 16,
      lineHeight: 1
    }
  }, "\xD7"));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function Checkbox({
  label,
  checked,
  defaultChecked,
  onChange,
  disabled,
  description
}) {
  const [c, setC] = React.useState(!!defaultChecked);
  const cur = checked ?? c;
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'flex',
      gap: 10,
      alignItems: 'flex-start',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? .5 : 1,
      font: 'var(--type-body)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => {
      if (disabled) return;
      setC(!cur);
      onChange && onChange(!cur);
    },
    style: {
      width: 18,
      height: 18,
      flex: 'none',
      marginTop: 1,
      borderRadius: 'var(--radius-xs)',
      border: `1px solid ${cur ? 'var(--cb-blue-500)' : 'var(--border-strong)'}`,
      background: cur ? 'var(--cb-blue-500)' : 'var(--surface-card)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      transition: 'background var(--duration-fast)'
    }
  }, cur && /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#fff",
    strokeWidth: "3",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M20 6 9 17l-5-5"
  }))), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'block',
      fontWeight: 500,
      lineHeight: '20px'
    }
  }, label), description && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'block',
      font: 'var(--type-body-sm)',
      color: 'var(--text-muted)'
    }
  }, description)));
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Input({
  label,
  hint,
  error,
  icon,
  size = 'md',
  style,
  inputStyle,
  ...rest
}) {
  const [f, setF] = React.useState(false);
  const h = size === 'sm' ? 32 : size === 'lg' ? 48 : 40;
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      font: 'var(--type-body)',
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--weight-medium) 13px/1 var(--font-sans)',
      color: 'var(--text-primary)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      height: h,
      padding: '0 12px',
      borderRadius: 'var(--radius-md)',
      background: 'var(--surface-card)',
      border: `1px solid ${error ? 'var(--status-danger)' : f ? 'var(--border-focus)' : 'var(--border-default)'}`,
      boxShadow: f ? 'var(--shadow-focus)' : 'var(--shadow-xs)',
      transition: 'box-shadow var(--duration-fast)'
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      width: 16,
      height: 16,
      color: 'var(--text-muted)'
    }
  }, icon), /*#__PURE__*/React.createElement("input", _extends({
    onFocus: () => setF(true),
    onBlur: () => setF(false),
    style: {
      all: 'unset',
      flex: 1,
      minWidth: 0,
      font: `400 ${size === 'lg' ? 15 : 14}px/1 var(--font-sans)`,
      color: 'var(--text-primary)',
      ...inputStyle
    }
  }, rest))), (hint || error) && /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-body-sm)',
      color: error ? 'var(--status-danger-text)' : 'var(--text-muted)'
    }
  }, error || hint));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Radio.jsx
try { (() => {
function Radio({
  options,
  value,
  onChange,
  name,
  direction = 'column'
}) {
  const [v, setV] = React.useState(value);
  const cur = value ?? v;
  return /*#__PURE__*/React.createElement("div", {
    role: "radiogroup",
    style: {
      display: 'flex',
      flexDirection: direction,
      gap: direction === 'row' ? 20 : 10
    }
  }, options.map(o => {
    const on = cur === o.value;
    return /*#__PURE__*/React.createElement("label", {
      key: o.value,
      onClick: () => {
        setV(o.value);
        onChange && onChange(o.value);
      },
      style: {
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        cursor: 'pointer',
        font: 'var(--type-body)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 18,
        height: 18,
        flex: 'none',
        marginTop: 1,
        borderRadius: '50%',
        border: `${on ? 5 : 1}px solid ${on ? 'var(--cb-blue-500)' : 'var(--border-strong)'}`,
        background: '#fff',
        transition: 'border var(--duration-fast)'
      }
    }), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'block',
        fontWeight: 500,
        lineHeight: '20px'
      }
    }, o.label), o.description && /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'block',
        font: 'var(--type-body-sm)',
        color: 'var(--text-muted)'
      }
    }, o.description)));
  }));
}
Object.assign(__ds_scope, { Radio });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Radio.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function Select({
  label,
  options = [],
  value,
  placeholder = 'Select…',
  onChange,
  size = 'md',
  style
}) {
  const [open, setOpen] = React.useState(false);
  const [v, setV] = React.useState(value);
  const cur = value ?? v;
  const sel = options.find(o => o.value === cur);
  const h = size === 'sm' ? 32 : 40;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      position: 'relative',
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--weight-medium) 13px/1 var(--font-sans)'
    }
  }, label), /*#__PURE__*/React.createElement("button", {
    onClick: () => setOpen(o => !o),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      height: h,
      padding: '0 12px',
      borderRadius: 'var(--radius-md)',
      border: '1px solid var(--border-default)',
      background: 'var(--surface-card)',
      font: 'var(--weight-medium) 14px/1 var(--font-sans)',
      color: sel ? 'var(--text-primary)' : 'var(--text-muted)',
      cursor: 'pointer',
      boxShadow: 'var(--shadow-xs)',
      minWidth: 120,
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("span", null, label && sel ? sel.label : sel ? sel.label : placeholder), /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "m7 15 5 5 5-5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m7 9 5-5 5 5"
  }))), open && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 'calc(100% + 4px)',
      left: 0,
      minWidth: '100%',
      zIndex: 40,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      boxShadow: 'var(--shadow-md)',
      padding: 4
    }
  }, options.map(o => /*#__PURE__*/React.createElement("div", {
    key: o.value,
    onClick: () => {
      setV(o.value);
      onChange && onChange(o.value);
      setOpen(false);
    },
    style: {
      padding: '8px 10px',
      borderRadius: 'var(--radius-sm)',
      font: '400 14px/1.2 var(--font-sans)',
      cursor: 'pointer',
      background: o.value === cur ? 'var(--surface-sunken)' : 'transparent'
    },
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-hover)',
    onMouseLeave: e => e.currentTarget.style.background = o.value === cur ? 'var(--surface-sunken)' : 'transparent'
  }, o.label))));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function Switch({
  label,
  checked,
  defaultChecked,
  onChange,
  disabled,
  size = 'md'
}) {
  const [c, setC] = React.useState(!!defaultChecked);
  const cur = checked ?? c;
  const w = size === 'sm' ? 32 : 40,
    h = size === 'sm' ? 18 : 22,
    k = h - 4;
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 10,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? .5 : 1,
      font: 'var(--type-body)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    role: "switch",
    "aria-checked": cur,
    onClick: () => {
      if (disabled) return;
      setC(!cur);
      onChange && onChange(!cur);
    },
    style: {
      width: w,
      height: h,
      borderRadius: 999,
      background: cur ? 'var(--cb-blue-500)' : 'var(--cb-stone-300)',
      position: 'relative',
      transition: 'background var(--duration-base) var(--ease-standard)',
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: 2,
      left: cur ? w - k - 2 : 2,
      width: k,
      height: k,
      borderRadius: '50%',
      background: '#fff',
      boxShadow: 'var(--shadow-sm)',
      transition: 'left var(--duration-base) var(--ease-standard)'
    }
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500
    }
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/Dashboard.jsx
try { (() => {
const {
  MetricCard,
  Badge,
  Button,
  VerdictChip
} = window.CrossBidDesignSystem_b81312;
function AskBar() {
  const [v, setV] = React.useState('');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 14,
      padding: '18px 22px 16px',
      boxShadow: 'var(--shadow-xs)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Icons.search, {
    size: 20,
    style: {
      color: 'var(--text-muted)'
    }
  }), /*#__PURE__*/React.createElement("input", {
    value: v,
    onChange: e => setV(e.target.value),
    placeholder: "Ask about any tender, @ to add a document",
    style: {
      all: 'unset',
      flex: 1,
      font: '400 17px/1 var(--font-sans)',
      color: 'var(--text-primary)'
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    icon: /*#__PURE__*/React.createElement(Icons.plus, {
      size: 16
    })
  }, "Upload tender"), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    icon: /*#__PURE__*/React.createElement(Icons.lang, {
      size: 16
    })
  }, "Bidder language: DE"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    iconRight: /*#__PURE__*/React.createElement(Icons.chev, {
      size: 14
    })
  }, "Thorough")));
}
function QuickActions({
  go
}) {
  const items = [['Analyse tender', 'file', true], ['Map certificates', 'layers', false], ['Check evidence', 'fileCheck', false], ['Review verdict', 'shield', true], ['Compare lots', 'box', false], ['Draft response', 'spark', false], ['Company profile', 'db', false]];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'center',
      gap: 28,
      margin: '28px 0 4px'
    }
  }, items.map(([l, ic, solid]) => {
    const I = Icons[ic];
    return /*#__PURE__*/React.createElement("button", {
      key: l,
      onClick: () => go(l === 'Review verdict' ? 'verdict' : 'matrix'),
      style: {
        all: 'unset',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 60,
        height: 60,
        borderRadius: 14,
        background: solid ? 'var(--surface-accent)' : 'var(--cb-blue-100)',
        color: solid ? '#fff' : 'var(--cb-blue-500)',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center'
      }
    }, /*#__PURE__*/React.createElement(I, {
      size: 24
    })), /*#__PURE__*/React.createElement("span", {
      style: {
        font: '400 14px/1 var(--font-sans)',
        color: 'var(--text-secondary)'
      }
    }, l));
  }));
}
function TenderTable({
  go,
  rows
}) {
  const ph = {
    Analysis: 'info',
    Review: 'warning',
    Confirmed: 'success'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 12,
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,2.2fr) 130px 150px minmax(0,1.6fr) 120px 170px',
      padding: '0 20px',
      height: 46,
      alignItems: 'center',
      font: '500 13px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "Tender ", /*#__PURE__*/React.createElement(Icons.chev, {
    size: 12,
    style: {
      verticalAlign: -1
    }
  })), /*#__PURE__*/React.createElement("span", null, "Due"), /*#__PURE__*/React.createElement("span", null, "Phase ", /*#__PURE__*/React.createElement(Icons.chev, {
    size: 12,
    style: {
      verticalAlign: -1
    }
  })), /*#__PURE__*/React.createElement("span", null, "Buyer"), /*#__PURE__*/React.createElement("span", null, "Value"), /*#__PURE__*/React.createElement("span", null, "Verdict")), rows.map((t, i) => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    onClick: () => go(t.verdict === 'conditional' ? 'verdict' : 'matrix'),
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-sunken)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent',
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,2.2fr) 130px 150px minmax(0,1.6fr) 120px 170px',
      padding: '0 20px',
      height: 56,
      alignItems: 'center',
      borderBottom: i < rows.length - 1 ? '1px solid var(--border-default)' : 'none',
      cursor: 'pointer',
      font: '400 14px/1.2 var(--font-sans)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-link)',
      fontWeight: 500,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
      paddingRight: 16
    }
  }, t.title), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      color: 'var(--text-secondary)'
    }
  }, /*#__PURE__*/React.createElement(Icons.clock, {
    size: 15
  }), t.due), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement(Badge, {
    tone: ph[t.phase],
    pill: false
  }, t.phase)), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)',
      textTransform: 'uppercase',
      fontSize: 13,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
      paddingRight: 16
    }
  }, t.buyer), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)'
    }
  }, t.value), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement(VerdictChip, {
    verdict: t.verdict,
    size: "sm"
  })))));
}
function Dashboard({
  go
}) {
  const d = window.CB_DATA;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Good afternoon, Lena"
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    icon: /*#__PURE__*/React.createElement(Icons.grid, {
      size: 16
    })
  }, "Customize")), /*#__PURE__*/React.createElement(AskBar, null), /*#__PURE__*/React.createElement(QuickActions, {
    go: go
  }), /*#__PURE__*/React.createElement(SectionHead, {
    title: "Key metrics",
    link: "View reports"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4,minmax(0,1fr))',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(MetricCard, {
    label: "Open tenders",
    value: "6",
    delta: "\u2191 2",
    period: "This week"
  }), /*#__PURE__*/React.createElement(MetricCard, {
    label: "Requirements checked",
    value: "187",
    delta: "\u2191 47",
    period: "Last 7 days"
  }), /*#__PURE__*/React.createElement(MetricCard, {
    label: "Verdicts awaiting review",
    value: "3",
    delta: "\u25B2 1",
    deltaTone: "neutral",
    period: "Current"
  }), /*#__PURE__*/React.createElement(MetricCard, {
    label: "Go rate",
    value: "50%",
    delta: "\u2191 8.3%",
    period: "YTD"
  })), /*#__PURE__*/React.createElement(SectionHead, {
    title: "Next 30 days",
    link: "View all tenders"
  }), /*#__PURE__*/React.createElement(TenderTable, {
    go: go,
    rows: d.tenders
  }));
}
Object.assign(window, {
  Dashboard
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/Dashboard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/Icons.jsx
try { (() => {
const Ic = (d, s = 18) => ({
  size = s,
  style
} = {}) => /*#__PURE__*/React.createElement("svg", {
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "1.75",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  style: style
}, d);
const Icons = {
  grid: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
    width: "7",
    height: "7",
    x: "3",
    y: "3",
    rx: "1"
  }), /*#__PURE__*/React.createElement("rect", {
    width: "7",
    height: "7",
    x: "14",
    y: "3",
    rx: "1"
  }), /*#__PURE__*/React.createElement("rect", {
    width: "7",
    height: "7",
    x: "14",
    y: "14",
    rx: "1"
  }), /*#__PURE__*/React.createElement("rect", {
    width: "7",
    height: "7",
    x: "3",
    y: "14",
    rx: "1"
  }))),
  box: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m3.3 7 8.7 5 8.7-5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 22V12"
  }))),
  file: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M14 2v4a2 2 0 0 0 2 2h4"
  }))),
  fileCheck: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M14 2v4a2 2 0 0 0 2 2h4"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m9 15 2 2 4-4"
  }))),
  shield: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m9 12 2 2 4-4"
  }))),
  spark: Ic(/*#__PURE__*/React.createElement("path", {
    d: "M9.9 2.1 12 8l5.9 2.1L12 12.2 9.9 18 7.8 12.2 2 10.1 7.8 8z"
  })),
  db: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("ellipse", {
    cx: "12",
    cy: "5",
    rx: "9",
    ry: "3"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3 5v14a9 3 0 0 0 18 0V5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3 12a9 3 0 0 0 18 0"
  }))),
  chart: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M3 3v16a2 2 0 0 0 2 2h16"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M18 17V9"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M13 17V5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 17v-3"
  }))),
  cal: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
    width: "18",
    height: "18",
    x: "3",
    y: "4",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M16 2v4M8 2v4M3 10h18"
  }))),
  clock: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 6v6l4 2"
  }))),
  ext: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M15 3h6v6"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M10 14 21 3"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"
  }))),
  check: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m9 12 2 2 4-4"
  }))),
  x: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m15 9-6 6M9 9l6 6"
  }))),
  alert: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 8v4M12 16h.01"
  }))),
  search: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "11",
    cy: "11",
    r: "8"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m21 21-4.3-4.3"
  }))),
  plus: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M5 12h14"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 5v14"
  }))),
  down: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M12 5v14"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m19 12-7 7-7-7"
  }))),
  chev: Ic(/*#__PURE__*/React.createElement("path", {
    d: "m6 9 6 6 6-6"
  })),
  sliders: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M21 4H3M21 12H3M21 20H3"
  }))),
  zap: Ic(/*#__PURE__*/React.createElement("path", {
    d: "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"
  })),
  line: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M3 3v16a2 2 0 0 0 2 2h16"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m19 9-5 5-4-4-3 3"
  }))),
  upload: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m17 8-5-5-5 5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 3v12"
  }))),
  lang: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "m5 8 6 6"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m4 14 6-6 2-3"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M2 5h12"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M7 2h1"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m22 22-5-10-5 10"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M14 18h6"
  }))),
  arrow: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M5 12h14"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m12 5 7 7-7 7"
  }))),
  dot: Ic(/*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "4",
    fill: "currentColor",
    stroke: "none"
  })),
  layers: Ic(/*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"
  })))
};
Object.assign(window, {
  Icons
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/Icons.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/Matrix.jsx
try { (() => {
const {
  Tabs,
  Button,
  Badge,
  Tag,
  Tooltip,
  VerdictChip,
  MetricCard,
  Select
} = window.CrossBidDesignSystem_b81312;
const STATE = {
  supported: ['success', 'Supported'],
  partial: ['warning', 'Partially supported'],
  unsupported: ['danger', 'Unsupported']
};
function ReqRow({
  r,
  open,
  onToggle
}) {
  const [tone, label] = STATE[r.state];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: onToggle,
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-sunken)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent',
    style: {
      display: 'grid',
      gridTemplateColumns: '92px 100px minmax(0,1fr) 120px 190px',
      gap: 16,
      padding: '14px 20px',
      alignItems: 'center',
      cursor: 'pointer',
      font: '400 14px/1.4 var(--font-sans)'
    }
  }, /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, r.id), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)'
    }
  }, r.cat), /*#__PURE__*/React.createElement("span", {
    style: {
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: open ? 'normal' : 'nowrap'
    }
  }, r.trans), /*#__PURE__*/React.createElement(Tooltip, {
    content: 'Open tender ' + r.src
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => e.preventDefault(),
    style: {
      font: 'var(--type-mono)',
      color: 'var(--text-link)',
      display: 'inline-flex',
      gap: 5,
      alignItems: 'center'
    }
  }, r.src, /*#__PURE__*/React.createElement(Icons.ext, {
    size: 12
  }))), /*#__PURE__*/React.createElement(Badge, {
    tone: tone
  }, label)), open && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '0 20px 18px 128px',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 12px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      marginBottom: 6,
      letterSpacing: '.04em'
    }
  }, "SOURCE (IT)"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.5 var(--font-sans)',
      color: 'var(--text-secondary)',
      fontStyle: 'italic'
    }
  }, "\u201C", r.orig, "\u201D")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 12px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      marginBottom: 6,
      letterSpacing: '.04em'
    }
  }, "EVIDENCE IN YOUR PROFILE"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.5 var(--font-sans)'
    }
  }, r.ev), r.state !== 'supported' && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10,
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    variant: "secondary",
    icon: /*#__PURE__*/React.createElement(Icons.upload, {
      size: 14
    })
  }, "Add evidence"), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    variant: "ghost"
  }, "Mark not applicable")))));
}
function Matrix({
  go
}) {
  const d = window.CB_DATA;
  const t = d.tenders[0];
  const [open, setOpen] = React.useState('REQ-012');
  const [tab, setTab] = React.useState('all');
  const rows = tab === 'all' ? d.requirements : d.requirements.filter(r => r.state !== 'supported');
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      go('dashboard');
    },
    style: {
      color: 'var(--text-muted)'
    }
  }, "Tenders"), /*#__PURE__*/React.createElement("span", null, "/"), /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-mono)'
    }
  }, t.id)), /*#__PURE__*/React.createElement(PageHeader, {
    title: t.title
  }, /*#__PURE__*/React.createElement(VerdictChip, {
    verdict: t.verdict,
    size: "lg"
  }), /*#__PURE__*/React.createElement(Button, {
    onClick: () => go('verdict'),
    icon: /*#__PURE__*/React.createElement(Icons.shield, {
      size: 16
    })
  }, "Review verdict")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      flexWrap: 'wrap',
      marginBottom: 24
    }
  }, /*#__PURE__*/React.createElement(Tag, null, t.buyer), /*#__PURE__*/React.createElement(Tag, null, "Italy \u2192 Germany"), /*#__PURE__*/React.createElement(Tag, null, "112 pages \xB7 IT"), /*#__PURE__*/React.createElement(Tag, null, "Due ", t.due.toLowerCase()), /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, "Lot 2")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4,minmax(0,1fr))',
      gap: 16,
      marginBottom: 28
    }
  }, /*#__PURE__*/React.createElement(MetricCard, {
    label: "Requirements extracted",
    value: "47",
    period: "all cited"
  }), /*#__PURE__*/React.createElement(MetricCard, {
    label: "Supported",
    value: "42",
    delta: "89%",
    period: "of requirements"
  }), /*#__PURE__*/React.createElement(MetricCard, {
    label: "Partially supported",
    value: "2",
    deltaTone: "neutral",
    delta: "\u25B2 \u2013",
    period: "need reference projects"
  }), /*#__PURE__*/React.createElement(MetricCard, {
    label: "Unsupported",
    value: "3",
    delta: "\u25BC 1",
    deltaTone: "danger",
    period: "since last run"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(Tabs, {
    variant: "underline",
    items: [{
      label: 'All requirements',
      value: 'all',
      count: 47
    }, {
      label: 'Needs evidence',
      value: 'gaps',
      count: 5
    }, {
      label: 'Certificates',
      value: 'c',
      count: 6
    }, {
      label: 'Lots',
      value: 'l',
      count: 3
    }],
    value: tab,
    onChange: v => setTab(v === 'c' || v === 'l' ? 'all' : v),
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Select, {
    placeholder: "Category",
    size: "sm",
    options: [{
      label: 'Selection',
      value: 's'
    }, {
      label: 'Technical',
      value: 't'
    }, {
      label: 'Award',
      value: 'a'
    }, {
      label: 'Formal',
      value: 'f'
    }]
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 12,
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '92px 100px minmax(0,1fr) 120px 190px',
      gap: 16,
      padding: '0 20px',
      height: 44,
      alignItems: 'center',
      font: '500 13px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      borderBottom: '1px solid var(--border-default)',
      background: 'var(--surface-sunken)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "ID"), /*#__PURE__*/React.createElement("span", null, "Category"), /*#__PURE__*/React.createElement("span", null, "Requirement (translated to DE \xB7 shown in EN)"), /*#__PURE__*/React.createElement("span", null, "Source"), /*#__PURE__*/React.createElement("span", null, "Evidence")), rows.map(r => /*#__PURE__*/React.createElement(ReqRow, {
    key: r.id,
    r: r,
    open: open === r.id,
    onToggle: () => setOpen(open === r.id ? null : r.id)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '12px 20px',
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-muted)'
    }
  }, "Showing ", rows.length, " of 47 \xB7 every line links to its page in the tender")));
}
Object.assign(window, {
  Matrix
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/Matrix.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/Runs.jsx
try { (() => {
const {
  Tabs,
  Button,
  Select,
  IconButton,
  Card,
  RunCard
} = window.CrossBidDesignSystem_b81312;
function ActivityChart() {
  const W = 760,
    H = 230,
    pad = 36;
  const ok = [0, 0, 0, 0, 0, 3, 0, 0, 2, 2, 1, 1],
    warn = [0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0],
    fail = [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0];
  const max = 6;
  const x = i => pad + i * (W - 2 * pad) / 11,
    y = v => H - 30 - v / max * (H - 60);
  const p = a => a.map((v, i) => (i ? 'L' : 'M') + x(i) + ',' + y(v)).join(' ');
  return /*#__PURE__*/React.createElement("svg", {
    viewBox: '0 0 ' + W + ' ' + H,
    style: {
      width: '100%',
      height: 'auto',
      display: 'block'
    }
  }, [0, 1, 2, 3].map(i => /*#__PURE__*/React.createElement("line", {
    key: i,
    x1: pad,
    x2: W - pad,
    y1: y(i * 2),
    y2: y(i * 2),
    stroke: "var(--chart-grid)",
    strokeDasharray: "4 4"
  })), /*#__PURE__*/React.createElement("path", {
    d: p(warn),
    fill: "none",
    stroke: "var(--chart-3)",
    strokeWidth: "2.5",
    strokeLinejoin: "round"
  }), /*#__PURE__*/React.createElement("path", {
    d: p(fail),
    fill: "none",
    stroke: "var(--chart-4)",
    strokeWidth: "2.5",
    strokeLinejoin: "round"
  }), /*#__PURE__*/React.createElement("path", {
    d: p(ok),
    fill: "none",
    stroke: "var(--chart-2)",
    strokeWidth: "2.5",
    strokeLinejoin: "round"
  }), ['May 22', 'May 28', 'Jun 3', 'Jun 9', 'Jun 15', 'Jun 21'].map((l, i) => /*#__PURE__*/React.createElement("text", {
    key: l,
    x: x(i * 11 / 5),
    y: H - 6,
    fontSize: "12",
    fill: "var(--text-muted)",
    textAnchor: "middle",
    fontFamily: "var(--font-sans)"
  }, l)));
}
function Donut() {
  const r = 44,
    c = 2 * Math.PI * r;
  const seg = [[10, 'var(--chart-2)'], [3, 'var(--chart-3)'], [1, 'var(--chart-4)']];
  let off = 0;
  return /*#__PURE__*/React.createElement("svg", {
    width: "130",
    height: "130",
    viewBox: "0 0 130 130"
  }, seg.map(([n, col], i) => {
    const len = n / 14 * c;
    const el = /*#__PURE__*/React.createElement("circle", {
      key: i,
      cx: "65",
      cy: "65",
      r: r,
      fill: "none",
      stroke: col,
      strokeWidth: "14",
      strokeDasharray: len + ' ' + (c - len),
      strokeDashoffset: -off,
      transform: "rotate(-90 65 65)"
    });
    off += len;
    return el;
  }), /*#__PURE__*/React.createElement("text", {
    x: "65",
    y: "63",
    textAnchor: "middle",
    fontSize: "28",
    fontWeight: "600",
    fill: "var(--text-primary)",
    fontFamily: "var(--font-sans)"
  }, "14"), /*#__PURE__*/React.createElement("text", {
    x: "65",
    y: "82",
    textAnchor: "middle",
    fontSize: "12",
    fill: "var(--text-muted)",
    fontFamily: "var(--font-sans)"
  }, "runs"));
}
function Legend({
  items
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 18,
      font: '400 14px/1 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, items.map(([l, c]) => /*#__PURE__*/React.createElement("span", {
    key: l,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 9,
      height: 9,
      borderRadius: '50%',
      background: c
    }
  }), l)));
}
function Runs({
  go
}) {
  const d = window.CB_DATA;
  const [tab, setTab] = React.useState('runs');
  const [f, setF] = React.useState();
  const rows = f ? d.runs.filter(r => r.status === f) : d.runs;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(PageHeader, {
    title: "Agent runs"
  }, /*#__PURE__*/React.createElement(Tabs, {
    items: [{
      label: 'Agents',
      value: 'agents'
    }, {
      label: 'Runs',
      value: 'runs'
    }],
    value: tab,
    onChange: setTab
  }), /*#__PURE__*/React.createElement(Button, {
    icon: /*#__PURE__*/React.createElement(Icons.plus, {
      size: 16
    })
  }, "Analyse tender")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) 340px',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "Agent activity",
    icon: /*#__PURE__*/React.createElement(Icons.line, {
      size: 20
    }),
    actions: /*#__PURE__*/React.createElement(Legend, {
      items: [['Succeeded', 'var(--chart-2)'], ['Failed', 'var(--chart-4)'], ['Needs attention', 'var(--chart-3)'], ['In progress', 'var(--chart-1)']]
    })
  }, /*#__PURE__*/React.createElement(ActivityChart, null)), /*#__PURE__*/React.createElement(Card, {
    title: "Status breakdown",
    icon: /*#__PURE__*/React.createElement(Icons.zap, {
      size: 20
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement(Donut, null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'auto auto auto',
      gap: '14px 12px',
      font: '400 14px/1 var(--font-sans)',
      alignItems: 'center'
    }
  }, [['Succeeded', 'var(--chart-2)', 10, '71%'], ['Failed', 'var(--chart-4)', 1, '7%'], ['Needs attention', 'var(--chart-3)', 3, '21%'], ['In progress', 'var(--chart-1)', 0, '0%']].map(([l, c, n, p]) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: l
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      color: 'var(--text-secondary)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 9,
      height: 9,
      borderRadius: '50%',
      background: c
    }
  }), l), /*#__PURE__*/React.createElement("b", {
    style: {
      fontWeight: 600
    }
  }, n), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, "(", p, ")"))))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      margin: '20px 0',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(Select, {
    placeholder: "Status",
    value: f,
    onChange: setF,
    options: [{
      label: 'Succeeded',
      value: 'success'
    }, {
      label: 'Needs attention',
      value: 'warning'
    }, {
      label: 'Failed',
      value: 'danger'
    }]
  }), /*#__PURE__*/React.createElement(Select, {
    placeholder: "Agent",
    options: [{
      label: 'Tender analysis',
      value: 'a'
    }, {
      label: 'Certificate mapping',
      value: 'b'
    }]
  }), /*#__PURE__*/React.createElement(Select, {
    placeholder: "Trigger",
    options: [{
      label: 'Manual',
      value: 'm'
    }, {
      label: 'Scheduled',
      value: 's'
    }]
  }), f && /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    onClick: () => setF(undefined)
  }, "Clear"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Select, {
    value: "s",
    options: [{
      label: 'Sorted by: Started',
      value: 's'
    }, {
      label: 'Sorted by: Duration',
      value: 'd'
    }]
  }), /*#__PURE__*/React.createElement(IconButton, {
    label: "Sort direction"
  }, /*#__PURE__*/React.createElement(Icons.down, {
    size: 16
  })), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    icon: /*#__PURE__*/React.createElement(Icons.sliders, {
      size: 16
    })
  }, "Customize")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, rows.map(r => /*#__PURE__*/React.createElement(RunCard, {
    key: r.title + r.meta[3],
    title: r.title,
    summary: r.summary,
    status: r.status,
    statusLabel: r.statusLabel,
    onAction: () => go(r.status === 'warning' ? 'verdict' : 'matrix'),
    meta: [{
      icon: /*#__PURE__*/React.createElement(Icons.cal, {
        size: 16
      }),
      label: r.meta[0]
    }, {
      icon: /*#__PURE__*/React.createElement(Icons.spark, {
        size: 16
      }),
      label: r.meta[1]
    }, {
      icon: /*#__PURE__*/React.createElement(Icons.clock, {
        size: 16
      }),
      label: r.meta[2]
    }, {
      label: r.meta[3]
    }]
  }))));
}
Object.assign(window, {
  Runs
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/Runs.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/Shell.jsx
try { (() => {
const {
  NavItem,
  Button,
  IconButton
} = window.CrossBidDesignSystem_b81312;
function Sidebar({
  route,
  go
}) {
  const Eye = ({
    c
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 12px/1 var(--font-sans)',
      letterSpacing: '.06em',
      color: 'var(--text-muted)',
      padding: '0 10px',
      margin: '24px 0 10px'
    }
  }, c);
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 'var(--sidebar-width)',
      flex: 'none',
      padding: '28px 20px',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      position: 'sticky',
      top: 0,
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      padding: '4px 8px'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/logo-lockup.png",
    alt: "CrossBid",
    style: {
      height: 30,
      display: 'block'
    }
  })), /*#__PURE__*/React.createElement(Eye, {
    c: "WORKFLOW"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.grid, null),
    label: "Dashboard",
    active: route === 'dashboard',
    onClick: () => go('dashboard')
  }), /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.file, null),
    label: "Tenders",
    active: route === 'tenders',
    onClick: () => go('matrix')
  }), /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.fileCheck, null),
    label: "Compliance",
    active: route === 'matrix',
    onClick: () => go('matrix')
  }), /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.layers, null),
    label: "Certificates",
    onClick: () => go('matrix')
  }), /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.shield, null),
    label: "Verdicts",
    active: route === 'verdict',
    tone: "solid",
    onClick: () => go('verdict')
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'var(--border-default)',
      margin: '24px 0 0'
    }
  }), /*#__PURE__*/React.createElement(Eye, {
    c: "PLATFORM"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.spark, null),
    label: "Agent runs",
    active: route === 'runs',
    onClick: () => go('runs')
  }), /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.db, null),
    label: "Company profile",
    trailing: /*#__PURE__*/React.createElement(Icons.chev, {
      size: 16
    })
  }), /*#__PURE__*/React.createElement(NavItem, {
    icon: /*#__PURE__*/React.createElement(Icons.chart, null),
    label: "Reports"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '10px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 32,
      height: 32,
      borderRadius: '50%',
      background: 'var(--cb-stone-200)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      font: '600 12px/1 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, "LH"), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 14px/1.2 var(--font-sans)'
    }
  }, "Lena Hartmann"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 12px/1.2 var(--font-sans)',
      color: 'var(--text-muted)'
    }
  }, "Nordvik Elektro GmbH"))));
}
function Frame({
  children
}) {
  return /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minWidth: 0,
      padding: '28px 28px 28px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 14,
      minHeight: 'calc(100vh - 56px)',
      padding: 32,
      boxShadow: 'var(--shadow-xs)'
    }
  }, children));
}
function PageHeader({
  title,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      marginBottom: 24
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      font: '600 30px/1.1 var(--font-sans)',
      letterSpacing: '-0.03em',
      margin: 0,
      flex: 1
    }
  }, title), children);
}
function SectionHead({
  title,
  link
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      margin: '28px 0 14px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '600 18px/1.2 var(--font-sans)',
      letterSpacing: '-0.02em'
    }
  }, title), link && /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: '500 14px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      display: 'inline-flex',
      gap: 6,
      alignItems: 'center'
    }
  }, link, " ", /*#__PURE__*/React.createElement(Icons.arrow, {
    size: 14
  })));
}
Object.assign(window, {
  Sidebar,
  Frame,
  PageHeader,
  SectionHead
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/Shell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/Verdict.jsx
try { (() => {
const {
  Button,
  Badge,
  Tag,
  Card,
  VerdictChip,
  Radio,
  Checkbox,
  Dialog,
  Toast
} = window.CrossBidDesignSystem_b81312;
function Verdict({
  go
}) {
  const d = window.CB_DATA;
  const t = d.tenders[0];
  const [choice, setChoice] = React.useState('conditional');
  const [ack, setAck] = React.useState(false);
  const [dlg, setDlg] = React.useState(false);
  const [done, setDone] = React.useState(false);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      go('dashboard');
    },
    style: {
      color: 'var(--text-muted)'
    }
  }, "Tenders"), /*#__PURE__*/React.createElement("span", null, "/"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      go('matrix');
    },
    style: {
      color: 'var(--text-muted)',
      font: 'var(--type-mono)'
    }
  }, t.id), /*#__PURE__*/React.createElement("span", null, "/"), /*#__PURE__*/React.createElement("span", null, "Verdict")), /*#__PURE__*/React.createElement(PageHeader, {
    title: "Review verdict"
  }, done ? /*#__PURE__*/React.createElement(VerdictChip, {
    verdict: choice,
    size: "lg",
    confirmed: true
  }) : /*#__PURE__*/React.createElement(Badge, {
    tone: "warning"
  }, "Awaiting your confirmation")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "CrossBid recommends",
    icon: /*#__PURE__*/React.createElement(Icons.spark, {
      size: 20
    }),
    actions: /*#__PURE__*/React.createElement(Tag, {
      mono: true
    }, "run 9 \xB7 Jun 21 09:02")
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(VerdictChip, {
    verdict: "conditional",
    size: "lg"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      font: '400 14px/1.4 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, "42 of 47 requirements supported. 3 cannot be verified from your profile.")), /*#__PURE__*/React.createElement("p", {
    style: {
      font: '400 15px/1.6 var(--font-sans)',
      margin: 0
    }
  }, "The tender is winnable on paper: turnover, ISO 9001 and chamber registration are all evidenced. The verdict is ", /*#__PURE__*/React.createElement("b", null, "Conditional"), ", not Go, because two selection criteria are unproven \u2014 a second reference project \u2265 \u20AC800k (", /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: 'var(--type-mono)',
      fontSize: 13
    }
  }, "REQ-031 \xB7 p. 22 \xA74.4"), ") and a guaranteed \u2264 4h maintenance response (", /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: 'var(--type-mono)',
      fontSize: 13
    }
  }, "REQ-044 \xB7 p. 31 \xA76.2"), "). SOA OS30 class III has no German equivalent; the buyer accepts equivalent proof under Art. 90 D.Lgs 36/2023 (", /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: 'var(--type-mono)',
      fontSize: 13
    }
  }, "p. 15 \xA73.2.c"), "), so HWK registration plus references should satisfy it."), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16,
      padding: '12px 14px',
      border: '1px solid var(--border-default)',
      borderRadius: 10,
      background: 'var(--surface-sunken)',
      font: '400 13px/1.5 var(--font-sans)',
      color: 'var(--text-secondary)',
      display: 'flex',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(Icons.alert, {
    size: 16,
    style: {
      flex: 'none',
      marginTop: 2
    }
  }), /*#__PURE__*/React.createElement("span", null, "Advisory only. CrossBid never submits and never asserts compliance without a source. This verdict does not move forward until you confirm it."))), /*#__PURE__*/React.createElement(Card, {
    title: "What would change the verdict",
    icon: /*#__PURE__*/React.createElement(Icons.fileCheck, {
      size: 20
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, [['REQ-031', 'Add a second comparable reference (≥ €800k, completed 2021–2024).', '→ Go if added'], ['REQ-044', 'Upload a service-level agreement or maintenance plan with ≤ 4h response.', '→ Go if added'], ['REQ-012', 'Attach the reference projects to satisfy SOA OS30 equivalence.', 'Strengthens position']].map(([id, txt, eff]) => /*#__PURE__*/React.createElement("div", {
    key: id,
    style: {
      display: 'grid',
      gridTemplateColumns: '90px minmax(0,1fr) auto',
      gap: 14,
      alignItems: 'center',
      font: '400 14px/1.4 var(--font-sans)'
    }
  }, /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, id), /*#__PURE__*/React.createElement("span", null, txt), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--status-success-text)',
      fontWeight: 500,
      fontSize: 13
    }
  }, eff)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "Your decision",
    icon: /*#__PURE__*/React.createElement(Icons.shield, {
      size: 20
    })
  }, /*#__PURE__*/React.createElement(Radio, {
    value: choice,
    onChange: setChoice,
    options: [{
      label: 'Go',
      value: 'go',
      description: 'Start drafting the response now.'
    }, {
      label: 'Conditional',
      value: 'conditional',
      description: 'Proceed while evidence for REQ-031 and REQ-044 is collected.'
    }, {
      label: 'No-go',
      value: 'nogo',
      description: 'Archive this tender. Reasons are kept for reporting.'
    }, {
      label: 'Insufficient evidence',
      value: 'insufficient',
      description: 'Hold — request documents from the buyer or your team.'
    }]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'var(--border-default)',
      margin: '18px 0'
    }
  }), /*#__PURE__*/React.createElement(Checkbox, {
    checked: ack,
    onChange: setAck,
    label: "I have reviewed the compliance matrix",
    description: "Required. Verdicts are never confirmed automatically."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      marginTop: 18
    }
  }, /*#__PURE__*/React.createElement(Button, {
    fullWidth: true,
    disabled: !ack || done,
    onClick: () => setDlg(true)
  }, "Confirm verdict"), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    onClick: () => go('matrix')
  }, "Back to matrix"))), /*#__PURE__*/React.createElement(Card, {
    title: "Reviewers",
    icon: /*#__PURE__*/React.createElement(Icons.db, {
      size: 20
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      font: '400 14px/1.3 var(--font-sans)'
    }
  }, [['LH', 'Lena Hartmann', 'Bid manager', done ? 'Confirmed' : 'Reviewing'], ['MK', 'Marek Kowalski', 'Technical lead', 'Not started']].map(([i, n, r, s]) => /*#__PURE__*/React.createElement("div", {
    key: n,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 30,
      height: 30,
      borderRadius: '50%',
      background: 'var(--cb-stone-200)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      font: '600 11px/1 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, i), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 500
    }
  }, n), /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, r)), /*#__PURE__*/React.createElement(Badge, {
    tone: s === 'Confirmed' ? 'success' : s === 'Reviewing' ? 'warning' : 'neutral',
    size: "sm"
  }, s))))))), /*#__PURE__*/React.createElement(Dialog, {
    open: dlg,
    onClose: () => setDlg(false),
    title: "Confirm verdict",
    description: /*#__PURE__*/React.createElement(React.Fragment, null, "This marks ", /*#__PURE__*/React.createElement("span", {
      style: {
        font: 'var(--type-mono)'
      }
    }, t.id), " as ", /*#__PURE__*/React.createElement("b", null, {
      go: 'Go',
      conditional: 'Conditional',
      nogo: 'No-go',
      insufficient: 'Insufficient evidence'
    }[choice]), ". ", choice === 'go' || choice === 'conditional' ? 'CrossBid will begin drafting the response — nothing is submitted.' : 'No drafting will start.', " You can revise the verdict at any time."),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "secondary",
      onClick: () => setDlg(false)
    }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
      onClick: () => {
        setDlg(false);
        setDone(true);
      }
    }, "Confirm verdict"))
  }), done && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'fixed',
      right: 24,
      bottom: 24,
      zIndex: 90
    }
  }, /*#__PURE__*/React.createElement(Toast, {
    tone: "success",
    title: "Verdict confirmed",
    description: 'Recorded by Lena Hartmann · ' + t.id,
    onDismiss: () => setDone(false)
  })));
}
Object.assign(window, {
  Verdict
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/Verdict.jsx", error: String((e && e.message) || e) }); }

// ui_kits/app/data.js
try { (() => {
window.CB_DATA = {
  tenders: [{
    id: '2024/S 118-345621',
    title: 'Modernisation of municipal wastewater treatment — Lot 2 (electrical)',
    buyer: 'Comune di Bergamo',
    country: 'IT',
    due: 'In 6 days',
    phase: 'Review',
    verdict: 'conditional',
    reqs: 47,
    unsupported: 3,
    value: '€2.4M'
  }, {
    id: '2024/S 121-352208',
    title: 'Framework agreement for IT security consulting services',
    buyer: 'Bundesamt für Sicherheit in der Informationstechnik',
    country: 'DE',
    due: 'In 9 days',
    phase: 'Analysis',
    verdict: 'insufficient',
    reqs: 31,
    unsupported: 0,
    value: '€850k'
  }, {
    id: '2024/S 115-339104',
    title: 'Supply and maintenance of medical imaging equipment',
    buyer: 'Région Auvergne-Rhône-Alpes',
    country: 'FR',
    due: 'In 12 days',
    phase: 'Review',
    verdict: 'go',
    reqs: 58,
    unsupported: 0,
    value: '€5.1M'
  }, {
    id: '2024/S 119-347810',
    title: 'Road resurfacing programme 2025–2027, north district',
    buyer: 'Gemeente Utrecht',
    country: 'NL',
    due: 'In 14 days',
    phase: 'Confirmed',
    verdict: 'nogo',
    reqs: 22,
    unsupported: 5,
    value: '€1.2M'
  }, {
    id: '2024/S 123-358443',
    title: 'Cloud hosting for citizen services portal',
    buyer: 'Skatteverket',
    country: 'SE',
    due: 'In 19 days',
    phase: 'Analysis',
    verdict: 'insufficient',
    reqs: 0,
    unsupported: 0,
    value: '€3.0M'
  }, {
    id: '2024/S 117-343002',
    title: 'School catering services, 14 sites',
    buyer: 'Ayuntamiento de Zaragoza',
    country: 'ES',
    due: 'In 21 days',
    phase: 'Review',
    verdict: 'go',
    reqs: 29,
    unsupported: 0,
    value: '€670k'
  }],
  runs: [{
    title: 'Tender analysis · 2024/S 118-345621',
    summary: 'Retrieved 47 requirements across 3 lots from 112 pages (IT). Translated to DE. Mapped 6 certificate requests; 3 requirements lack supporting evidence in the company profile (REQ-012, REQ-031, REQ-044).',
    status: 'warning',
    meta: ['Manual', '9 steps', '4 minutes', 'Jun 21 at 9:02 AM']
  }, {
    title: 'Certificate mapping · 2024/S 115-339104',
    summary: 'Mapped 4 French certificate requests to German equivalents: Qualibat 1552 → HWK Meisterbrief (Elektrotechnik); Attestation URSSAF → Unbedenklichkeitsbescheinigung. All 4 supported.',
    status: 'success',
    meta: ['Scheduled', '5 steps', '1 minute', 'Jun 21 at 9:00 AM']
  }, {
    title: 'Tender analysis · 2024/S 123-358443',
    summary: 'No verdict — the selection criteria (p. 14–17) are scanned images and not machine-readable. Upload a text version to continue.',
    status: 'danger',
    statusLabel: 'Failed',
    meta: ['Manual', '3 steps', '40 seconds', 'Jun 20 at 4:15 PM']
  }, {
    title: 'Tender analysis · 2024/S 117-343002',
    summary: 'Retrieved 29 requirements from 48 pages (ES). All requirements supported by profile evidence. Recommended verdict: Go. Awaiting confirmation by Lena Hartmann.',
    status: 'success',
    meta: ['Manual', '8 steps', '3 minutes', 'Jun 20 at 11:30 AM']
  }],
  requirements: [{
    id: 'REQ-001',
    cat: 'Selection',
    src: 'p. 14 §3.1.a',
    orig: 'Iscrizione alla Camera di Commercio per attività attinenti all\'oggetto dell\'appalto.',
    trans: 'Registration with the chamber of commerce for activities relevant to the contract.',
    ev: 'Handelsregisterauszug HRB 224871',
    state: 'supported'
  }, {
    id: 'REQ-002',
    cat: 'Selection',
    src: 'p. 14 §3.1.b',
    orig: 'Fatturato globale minimo annuo di € 3.000.000 negli ultimi tre esercizi.',
    trans: 'Minimum annual global turnover of €3,000,000 in each of the last three financial years.',
    ev: 'Jahresabschluss 2021–2023 (€3.6M / €4.1M / €4.4M)',
    state: 'supported'
  }, {
    id: 'REQ-012',
    cat: 'Selection',
    src: 'p. 15 §3.2.c',
    orig: 'Certificazione SOA categoria OS30 classifica III.',
    trans: 'SOA qualification, category OS30 (electrical systems), class III. No direct DE equivalent — closest: HWK Eintragung Elektrotechnik + reference projects ≥ €1.03M.',
    ev: 'HWK Eintragung found; reference projects missing',
    state: 'partial'
  }, {
    id: 'REQ-018',
    cat: 'Technical',
    src: 'p. 17 §4.1',
    orig: 'Certificazione UNI EN ISO 9001:2015 in corso di validità.',
    trans: 'Valid ISO 9001:2015 certification.',
    ev: 'ISO 9001:2015 · TÜV Rheinland · valid to 03/2027',
    state: 'supported'
  }, {
    id: 'REQ-031',
    cat: 'Technical',
    src: 'p. 22 §4.4',
    orig: 'Almeno due contratti analoghi eseguiti nel triennio, ciascuno di importo ≥ € 800.000.',
    trans: 'At least two comparable contracts completed in the last three years, each worth ≥ €800,000.',
    ev: 'One reference found (Stadtwerke Bonn, €1.1M). Second not found.',
    state: 'unsupported'
  }, {
    id: 'REQ-044',
    cat: 'Award',
    src: 'p. 31 §6.2',
    orig: 'Piano di manutenzione con tempi di intervento garantiti ≤ 4 ore.',
    trans: 'Maintenance plan with guaranteed response time ≤ 4 hours.',
    ev: 'No service-level document in profile',
    state: 'unsupported'
  }, {
    id: 'REQ-047',
    cat: 'Formal',
    src: 'p. 38 §8.1',
    orig: 'Garanzia provvisoria pari al 2% dell\'importo a base di gara.',
    trans: 'Bid bond equal to 2% of the estimated contract value (€48,000).',
    ev: 'Bank guarantee facility · Commerzbank · up to €250k',
    state: 'supported'
  }]
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/app/data.js", error: String((e && e.message) || e) }); }

// ui_kits/loader.js
try { (() => {
// Loads CrossBid DS components (bundle if present, else compiles component .jsx sources), then the kit's own babel files in order.
window.CBLoad = async function (root, kitFiles, mount) {
  const NS = 'CrossBidDesignSystem_b81312';
  const comps = ['core/Button', 'core/IconButton', 'core/Badge', 'core/Tag', 'core/Card', 'core/Tabs', 'core/Tooltip', 'forms/Input', 'forms/Select', 'forms/Checkbox', 'forms/Radio', 'forms/Switch', 'feedback/Dialog', 'feedback/Toast', 'app/NavItem', 'app/MetricCard', 'app/VerdictChip', 'app/RunCard'];
  if (!window[NS] || !window[NS].Button) {
    const ns = {};
    window[NS] = ns;
    for (const c of comps) {
      const name = c.split('/')[1];
      const t = await (await fetch(root + '/components/' + c + '.jsx')).text();
      const deps = [...t.matchAll(/import \{([^}]+)\} from/g)].flatMap(m => m[1].split(',').map(s => s.trim()));
      const src = t.replace(/^import .*$/gm, '').replace(/^export /gm, '') + '\n__r(' + name + ');';
      const code = Babel.transform(src, {
        presets: ['react'],
        filename: c + '.jsx'
      }).code;
      new Function('React', '__r', ...deps, code)(React, v => ns[name] = v, ...deps.map(d => ns[d]));
    }
  }
  for (const f of kitFiles) {
    const t = await (await fetch(f)).text();
    const code = Babel.transform(t, {
      presets: ['react'],
      filename: f
    }).code;
    (0, eval)(code);
  }
  if (mount) mount();
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/loader.js", error: String((e && e.message) || e) }); }

// ui_kits/website/Footer.jsx
try { (() => {
function Footer() {
  const cols = [['Product', ['How it works', 'Certificate equivalence', 'Compliance matrix', 'Pricing']], ['Company', ['About', 'Customers', 'Careers', 'Contact']], ['Resources', ['Documentation', 'EU procurement guide', 'Security', 'Status']], ['Legal', ['Privacy', 'Terms', 'Data processing', 'Imprint']]];
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: '1px solid var(--border-default)',
      padding: '56px 24px 40px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--marketing-max)',
      margin: '0 auto',
      display: 'grid',
      gridTemplateColumns: '1.4fr repeat(4,minmax(0,1fr))',
      gap: 32
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/logo-lockup.png",
    alt: "CrossBid",
    style: {
      height: 28,
      display: 'block'
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.55 var(--font-sans)',
      color: 'var(--text-secondary)',
      marginTop: 14,
      maxWidth: 280
    }
  }, "Go / no-go for EU public tenders, with a citation for every line.")), cols.map(([h, ls]) => /*#__PURE__*/React.createElement("div", {
    key: h
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 13px/1 var(--font-sans)',
      marginBottom: 14
    }
  }, h), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, ls.map(l => /*#__PURE__*/React.createElement("a", {
    key: l,
    href: "#",
    style: {
      font: '400 14px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      textDecoration: 'none'
    }
  }, l)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--marketing-max)',
      margin: '40px auto 0',
      paddingTop: 24,
      borderTop: '1px solid var(--border-default)',
      display: 'flex',
      justifyContent: 'space-between',
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "\xA9 2026 CrossBid"), /*#__PURE__*/React.createElement("span", null, "Made in the EU \xB7 Data stays in the EU")));
}
Object.assign(window, {
  Footer
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Footer.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Hero.jsx
try { (() => {
const {
  Button,
  Badge,
  Tag,
  VerdictChip
} = window.CrossBidDesignSystem_b81312;
function ProductFrame() {
  const rows = [['REQ-001', 'Chamber of commerce registration', 'p. 14 §3.1.a', 'success', 'Supported'], ['REQ-012', 'SOA OS30 class III → HWK + references', 'p. 15 §3.2.c', 'warning', 'Partially supported'], ['REQ-018', 'ISO 9001:2015, valid', 'p. 17 §4.1', 'success', 'Supported'], ['REQ-031', 'Two comparable contracts ≥ €800k', 'p. 22 §4.4', 'danger', 'Unsupported']];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 980,
      margin: '56px auto 0',
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 16,
      boxShadow: 'var(--shadow-lg)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '12px 16px',
      borderBottom: '1px solid var(--border-default)',
      background: 'var(--surface-sunken)'
    }
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 10,
      height: 10,
      borderRadius: '50%',
      background: 'var(--cb-stone-300)'
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 12,
      font: 'var(--type-mono)',
      color: 'var(--text-muted)'
    }
  }, "app.crossbid.eu / tenders / 2024-S-118-345621")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 28,
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) 300px',
      gap: 24,
      textAlign: 'left'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      marginBottom: 14,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(Tag, null, "Comune di Bergamo"), /*#__PURE__*/React.createElement(Tag, null, "Italy \u2192 Germany"), /*#__PURE__*/React.createElement(Tag, null, "112 pages \xB7 IT")), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '600 20px/1.25 var(--font-sans)',
      letterSpacing: '-0.02em',
      marginBottom: 18
    }
  }, "Modernisation of municipal wastewater treatment \u2014 Lot 2 (electrical)"), /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 10,
      overflow: 'hidden'
    }
  }, rows.map(([id, t, s, tone, l], i) => /*#__PURE__*/React.createElement("div", {
    key: id,
    style: {
      display: 'grid',
      gridTemplateColumns: '82px minmax(0,1fr) 104px 150px',
      gap: 12,
      alignItems: 'center',
      padding: '11px 14px',
      borderTop: i ? '1px solid var(--border-default)' : 'none',
      font: '400 13px/1.3 var(--font-sans)'
    }
  }, /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, id), /*#__PURE__*/React.createElement("span", {
    style: {
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, t), /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-mono)',
      fontSize: 11,
      color: 'var(--text-link)'
    }
  }, s), /*#__PURE__*/React.createElement(Badge, {
    tone: tone,
    size: "sm"
  }, l))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 12,
      padding: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      marginBottom: 10
    }
  }, "CrossBid recommends"), /*#__PURE__*/React.createElement(VerdictChip, {
    verdict: "conditional",
    size: "lg"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 13px/1.5 var(--font-sans)',
      color: 'var(--text-secondary)',
      marginTop: 12
    }
  }, "42 of 47 requirements supported. Two selection criteria need evidence before this becomes a Go.")), /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-default)',
      borderRadius: 12,
      padding: 18,
      background: 'var(--surface-sunken)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      marginBottom: 10
    }
  }, "Awaiting review"), /*#__PURE__*/React.createElement(Button, {
    fullWidth: true,
    size: "sm"
  }, "Confirm verdict"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 12px/1.4 var(--font-sans)',
      color: 'var(--text-muted)',
      marginTop: 8
    }
  }, "Nothing moves forward until a person confirms."))))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      left: 0,
      right: 0,
      bottom: -1,
      height: 140,
      background: 'var(--protect-gradient)',
      pointerEvents: 'none'
    }
  }));
}
function Hero() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      position: 'relative',
      overflow: 'hidden',
      padding: '96px 24px 0',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    "aria-hidden": true,
    style: {
      position: 'absolute',
      inset: 0,
      backgroundImage: 'linear-gradient(var(--cb-stone-200) 1px,transparent 1px),linear-gradient(90deg,var(--cb-stone-200) 1px,transparent 1px)',
      backgroundSize: '72px 72px',
      opacity: .35,
      maskImage: 'radial-gradient(ellipse 70% 60% at 50% 20%,#000 30%,transparent 100%)',
      WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 50% 20%,#000 30%,transparent 100%)',
      pointerEvents: 'none'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      maxWidth: 'var(--marketing-max)',
      margin: '0 auto'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 12px 6px 8px',
      borderRadius: 999,
      border: '1px solid var(--border-default)',
      background: 'var(--surface-card)',
      font: '500 13px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      marginBottom: 28
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      padding: '3px 8px',
      borderRadius: 999,
      background: 'var(--cb-orange-500)',
      color: '#fff',
      font: '600 11px/1.2 var(--font-sans)'
    }
  }, "New"), "Certificate equivalence for all 27 EU member states"), /*#__PURE__*/React.createElement("h1", {
    style: {
      font: '600 64px/1.05 var(--font-sans)',
      letterSpacing: '-0.035em',
      margin: '0 auto',
      maxWidth: 820,
      textWrap: 'balance'
    }
  }, "Know if you can win before you write a word."), /*#__PURE__*/React.createElement("p", {
    style: {
      font: '400 19px/1.55 var(--font-sans)',
      color: 'var(--text-secondary)',
      maxWidth: 620,
      margin: '24px auto 0',
      textWrap: 'pretty'
    }
  }, "CrossBid reads any EU tender, maps every requirement to your evidence, and gives you a go / no-go verdict you can defend \u2014 with a citation for each line."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      justifyContent: 'center',
      marginTop: 32
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "inverse",
    size: "lg",
    iconRight: /*#__PURE__*/React.createElement(Icons.arrow, {
      size: 16
    })
  }, "Analyse a tender"), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "lg"
  }, "Book a demo")), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 13px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      marginTop: 16
    }
  }, "Advisory by design \u2014 CrossBid never submits on your behalf."), /*#__PURE__*/React.createElement(ProductFrame, null)));
}
Object.assign(window, {
  Hero
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Hero.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Nav.jsx
try { (() => {
const {
  Button
} = window.CrossBidDesignSystem_b81312;
function Nav() {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 50,
      background: 'rgba(250,250,249,0.8)',
      backdropFilter: 'var(--blur-glass)',
      WebkitBackdropFilter: 'var(--blur-glass)',
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--marketing-max)',
      margin: '0 auto',
      padding: '0 24px',
      height: 68,
      display: 'flex',
      alignItems: 'center',
      gap: 32
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      display: 'flex',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/logo-lockup.png",
    alt: "CrossBid",
    style: {
      height: 30,
      display: 'block'
    }
  })), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      gap: 28,
      flex: 1,
      justifyContent: 'center'
    }
  }, ['Product', 'How it works', 'Certificates', 'Pricing', 'Customers'].map(l => /*#__PURE__*/React.createElement("a", {
    key: l,
    href: "#",
    style: {
      font: '500 14px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      textDecoration: 'none'
    }
  }, l))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm"
  }, "Sign in"), /*#__PURE__*/React.createElement(Button, {
    variant: "inverse",
    size: "sm"
  }, "Book a demo"))));
}
Object.assign(window, {
  Nav
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Nav.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Sections.jsx
try { (() => {
const {
  Button,
  Badge,
  Tag,
  VerdictChip
} = window.CrossBidDesignSystem_b81312;
const Wrap = ({
  children,
  style
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    maxWidth: 'var(--marketing-max)',
    margin: '0 auto',
    padding: '0 24px',
    ...style
  }
}, children);
const Eyebrow = ({
  c
}) => /*#__PURE__*/React.createElement("div", {
  style: {
    font: '500 12px/1 var(--font-sans)',
    letterSpacing: '.08em',
    textTransform: 'uppercase',
    color: 'var(--text-accent)',
    marginBottom: 14
  }
}, c);
const H2 = ({
  c
}) => /*#__PURE__*/React.createElement("h2", {
  style: {
    font: '600 40px/1.1 var(--font-sans)',
    letterSpacing: '-0.03em',
    margin: 0,
    textWrap: 'balance'
  }
}, c);
const Lead = ({
  c,
  center
}) => /*#__PURE__*/React.createElement("p", {
  style: {
    font: '400 17px/1.6 var(--font-sans)',
    color: 'var(--text-secondary)',
    margin: center ? '16px auto 0' : '16px 0 0',
    maxWidth: 560,
    textWrap: 'pretty'
  }
}, c);
function TrustLine() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '72px 0 0'
    }
  }, /*#__PURE__*/React.createElement(Wrap, {
    style: {
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      marginBottom: 24
    }
  }, "Used by bid teams tendering across borders"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'center',
      gap: 44,
      flexWrap: 'wrap',
      opacity: .7
    }
  }, ['Nordvik Elektro', 'Baumann & Söhne', 'Tecnoimpianti', 'Groupe Vallière', 'Ostrava Rail', 'Ibérica Redes'].map(n => /*#__PURE__*/React.createElement("span", {
    key: n,
    style: {
      font: '600 17px/1 var(--font-sans)',
      letterSpacing: '-0.02em',
      color: 'var(--text-secondary)'
    }
  }, n)))));
}
function Steps() {
  const s = [['Read', 'Upload the tender in any EU language. CrossBid extracts every requirement — selection, technical, award, formal — each with a link to its source page.', /*#__PURE__*/React.createElement(Icons.file, {
    size: 22
  })], ['Translate & explain', 'Each requirement is translated into your language and explained in plain terms, including what the buyer will accept as proof.', /*#__PURE__*/React.createElement(Icons.lang, {
    size: 22
  })], ['Map certificates', 'Requested certificates are matched to their equivalents in your home country — SOA to HWK, Qualibat to Meisterbrief — with the legal basis.', /*#__PURE__*/React.createElement(Icons.layers, {
    size: 22
  })], ['Check evidence', 'Every requirement is checked against your company profile. Supported, partial, or unsupported — never assumed.', /*#__PURE__*/React.createElement(Icons.fileCheck, {
    size: 22
  })], ['Verdict', 'Go, No-go, Conditional, or Insufficient evidence — with the compliance matrix behind it. A person confirms before anything proceeds.', /*#__PURE__*/React.createElement(Icons.shield, {
    size: 22
  })]];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '128px 0 0'
    }
  }, /*#__PURE__*/React.createElement(Wrap, null, /*#__PURE__*/React.createElement(Eyebrow, {
    c: "How it works"
  }), /*#__PURE__*/React.createElement(H2, {
    c: "Judgement work, done before the bid is written."
  }), /*#__PURE__*/React.createElement(Lead, {
    c: "Five steps, each one traceable to the tender and to your own documents."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))',
      gap: 16,
      marginTop: 48
    }
  }, s.map(([t, d, ic], i) => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 14,
      padding: 22,
      boxShadow: 'var(--shadow-xs)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 44,
      height: 44,
      borderRadius: 12,
      background: i === 4 ? 'var(--cb-ink)' : 'var(--surface-accent-soft)',
      color: i === 4 ? '#fff' : 'var(--text-accent)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, ic), /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-mono)',
      color: 'var(--text-muted)'
    }
  }, "0", i + 1)), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '600 17px/1.2 var(--font-sans)',
      letterSpacing: '-0.02em',
      marginBottom: 8
    }
  }, t), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.55 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, d))))));
}
function Features() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '128px 0 0'
    }
  }, /*#__PURE__*/React.createElement(Wrap, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)',
      gap: 64,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, {
    c: "Every requirement, cited"
  }), /*#__PURE__*/React.createElement(H2, {
    c: "No claim without a page number."
  }), /*#__PURE__*/React.createElement(Lead, {
    c: "Each extracted line links to the exact page and clause in the tender. Reviewers check the source, not the summary."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
      marginTop: 32
    }
  }, [['Source-linked extraction', 'Page and clause reference on every requirement.'], ['Translated, not paraphrased', 'Original text kept alongside the explanation.'], ['Refuses when unsure', 'If the documents don\'t support a verdict, CrossBid says so.']].map(([t, d]) => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      display: 'flex',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 22,
      height: 22,
      borderRadius: '50%',
      background: 'var(--status-success-bg)',
      color: 'var(--status-success)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      flex: 'none',
      marginTop: 1
    }
  }, /*#__PURE__*/React.createElement(Icons.check, {
    size: 14
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 15px/1.3 var(--font-sans)'
    }
  }, t), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.5 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, d)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 16,
      padding: 24,
      boxShadow: 'var(--shadow-md)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, "REQ-012"), /*#__PURE__*/React.createElement("span", {
    style: {
      font: '500 13px/1 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, "Selection \xB7 "), /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: 'var(--type-mono)',
      color: 'var(--text-link)',
      display: 'inline-flex',
      gap: 5,
      alignItems: 'center'
    }
  }, "p. 15 \xA73.2.c", /*#__PURE__*/React.createElement(Icons.ext, {
    size: 12
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 12px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      letterSpacing: '.04em',
      marginBottom: 6
    }
  }, "SOURCE (IT)"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: 'italic 400 14px/1.5 var(--font-sans)',
      color: 'var(--text-secondary)',
      marginBottom: 16
    }
  }, "\u201CCertificazione SOA categoria OS30 classifica III.\u201D"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 12px/1 var(--font-sans)',
      color: 'var(--text-muted)',
      letterSpacing: '.04em',
      marginBottom: 6
    }
  }, "EXPLAINED (DE \u2192 shown in EN)"), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.5 var(--font-sans)',
      marginBottom: 16
    }
  }, "SOA qualification, category OS30 (electrical systems), class III. No direct German equivalent \u2014 the buyer accepts equivalent proof under Art. 90 D.Lgs 36/2023: HWK registration for Elektrotechnik plus reference projects \u2265 \u20AC1.03M."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      paddingTop: 16,
      borderTop: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "warning"
  }, "Partially supported"), /*#__PURE__*/React.createElement("span", {
    style: {
      font: '400 13px/1.3 var(--font-sans)',
      color: 'var(--text-secondary)'
    }
  }, "HWK registration found \xB7 reference projects missing"))))));
}
function Certificates() {
  const rows = [['IT', 'SOA OS30 cl. III', 'DE', 'HWK Eintragung + Referenzen', 'D.Lgs 36/2023 Art. 90'], ['FR', 'Qualibat 1552', 'DE', 'Meisterbrief Elektrotechnik', 'Dir. 2014/24 Art. 60'], ['FR', 'Attestation URSSAF', 'DE', 'Unbedenklichkeits­bescheinigung', 'Dir. 2014/24 Art. 60'], ['ES', 'Clasificación Grupo I', 'NL', 'Erkenning + omzetverklaring', 'Dir. 2014/24 Ann. XII']];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '128px 0 0'
    }
  }, /*#__PURE__*/React.createElement(Wrap, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.15fr)',
      gap: 56,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 14,
      overflow: 'hidden',
      boxShadow: 'var(--shadow-xs)',
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '36px minmax(0,1fr) 36px minmax(0,1fr) minmax(0,1fr)',
      gap: 12,
      padding: '12px 18px',
      font: '500 12px/1 var(--font-sans)',
      color: 'var(--text-secondary)',
      background: 'var(--surface-sunken)',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null, "Requested"), /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null, "Your equivalent"), /*#__PURE__*/React.createElement("span", null, "Basis")), rows.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'grid',
      gridTemplateColumns: '36px minmax(0,1fr) 36px minmax(0,1fr) minmax(0,1fr)',
      gap: 12,
      padding: '13px 18px',
      alignItems: 'center',
      borderTop: i ? '1px solid var(--border-default)' : 'none',
      font: '400 13px/1.3 var(--font-sans)',
      overflowWrap: 'anywhere'
    }
  }, /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, r[0]), /*#__PURE__*/React.createElement("span", null, r[1]), /*#__PURE__*/React.createElement(Tag, {
    mono: true
  }, r[2]), /*#__PURE__*/React.createElement("span", null, r[3]), /*#__PURE__*/React.createElement("span", {
    style: {
      font: 'var(--type-mono)',
      fontSize: 11,
      color: 'var(--text-muted)',
      lineHeight: 1.4
    }
  }, r[4])))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, {
    c: "Certificate equivalence"
  }), /*#__PURE__*/React.createElement(H2, {
    c: "The buyer asks in their system. You answer in yours."
  }), /*#__PURE__*/React.createElement(Lead, {
    c: "CrossBid maps requested certificates and registrations to their equivalents in your home country, and cites the directive or national rule that makes the equivalence valid."
  })))));
}
function Advisory() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '128px 0 0'
    }
  }, /*#__PURE__*/React.createElement(Wrap, null, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-inverse)',
      color: '#fff',
      borderRadius: 24,
      padding: '72px 64px',
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1.1fr) minmax(0,1fr)',
      gap: 56,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 12px/1 var(--font-sans)',
      letterSpacing: '.08em',
      textTransform: 'uppercase',
      color: 'var(--cb-orange-500)',
      marginBottom: 14
    }
  }, "Advisory by design"), /*#__PURE__*/React.createElement("h2", {
    style: {
      font: '600 40px/1.1 var(--font-sans)',
      letterSpacing: '-0.03em',
      margin: 0,
      textWrap: 'balance'
    }
  }, "An agent that knows what it doesn't know."), /*#__PURE__*/React.createElement("p", {
    style: {
      font: '400 17px/1.6 var(--font-sans)',
      color: 'var(--cb-stone-300)',
      margin: '16px 0 0',
      maxWidth: 520
    }
  }, "CrossBid never submits a bid, never asserts compliance without a source, and withholds a verdict when the documents don't support one. Every verdict is confirmed by a person before drafting begins.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gap: 12
    }
  }, [['Never submits', 'Drafting help only after a human confirms the verdict.'], ['Never asserts without a source', 'Each compliance claim points at a page in the tender and a document in your profile.'], ['Refuses when unsupported', '“Insufficient evidence” is a first-class verdict, not a failure state.']].map(([t, d]) => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: 12,
      padding: '16px 18px',
      background: 'rgba(255,255,255,0.04)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '500 15px/1.3 var(--font-sans)'
    }
  }, t), /*#__PURE__*/React.createElement("div", {
    style: {
      font: '400 14px/1.5 var(--font-sans)',
      color: 'var(--cb-stone-400)',
      marginTop: 4
    }
  }, d)))))));
}
function CTA() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '128px 0'
    }
  }, /*#__PURE__*/React.createElement(Wrap, {
    style: {
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement(H2, {
    c: "Bring a tender. Leave with a verdict."
  }), /*#__PURE__*/React.createElement(Lead, {
    center: true,
    c: "Upload one tender and see the compliance matrix in minutes. No integration required."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      justifyContent: 'center',
      marginTop: 32
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "inverse",
    size: "lg",
    iconRight: /*#__PURE__*/React.createElement(Icons.arrow, {
      size: 16
    })
  }, "Analyse a tender"), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "lg"
  }, "Talk to the team"))));
}
Object.assign(window, {
  TrustLine,
  Steps,
  Features,
  Certificates,
  Advisory,
  CTA
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Sections.jsx", error: String((e && e.message) || e) }); }

__ds_ns.MetricCard = __ds_scope.MetricCard;

__ds_ns.NavItem = __ds_scope.NavItem;

__ds_ns.RunCard = __ds_scope.RunCard;

__ds_ns.VerdictChip = __ds_scope.VerdictChip;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Radio = __ds_scope.Radio;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

})();
