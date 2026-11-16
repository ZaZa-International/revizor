import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement>;

const base = (props: P) => ({
  viewBox: '0 0 24 24',
  className: `icon ${props.className ?? ''}`.trim(),
  'aria-hidden': true,
  ...props,
});

export const IconOverview = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z" />
  </svg>
);

export const IconMap = (p: P) => (
  <svg {...base(p)}>
    <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15" />
  </svg>
);

export const IconAsset = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3 3 8v8l9 5 9-5V8zM3 8l9 5 9-5M12 13v8" />
  </svg>
);

export const IconObservation = (p: P) => (
  <svg {...base(p)}>
    <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z" />
    <circle cx="12" cy="12" r="2.6" />
  </svg>
);

export const IconDefect = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3 2 20h20zM12 9.5v4.5M12 17.2v.6" />
  </svg>
);

export const IconReview = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 11.5 11.5 14 16 8.5" />
    <path d="M12 3a9 9 0 1 0 9 9" />
    <path d="M21 3v6h-6" />
  </svg>
);

export const IconJob = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M4 12h10M4 17h7" />
    <circle cx="18.5" cy="16.5" r="3.5" />
    <path d="M18.5 15v1.8l1.2 1" />
  </svg>
);

export const IconRoute = (p: P) => (
  <svg {...base(p)}>
    <circle cx="5" cy="18" r="2.2" />
    <circle cx="19" cy="6" r="2.2" />
    <path d="M7 18h6a4 4 0 0 0 0-8H9a3 3 0 0 1 0-6h8" strokeDasharray="0" />
  </svg>
);

export const IconAnalytics = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 20h16M7 16v-5M12 16V6M17 16v-8" />
  </svg>
);

export const IconExport = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3v11M8 10l4 4 4-4M4 17v3h16v-3" />
  </svg>
);

export const IconSearch = (p: P) => (
  <svg {...base(p)}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m15.5 15.5 5 5" />
  </svg>
);

export const IconPlus = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const IconClose = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="m4.5 12.5 5 5 10-11" />
  </svg>
);

export const IconAlert = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5v5.5M12 16.4v.4" />
  </svg>
);

export const IconChevronDown = (p: P) => (
  <svg {...base(p)}>
    <path d="m6 9 6 6 6-6" />
  </svg>
);

export const IconChevronLeft = (p: P) => (
  <svg {...base(p)}>
    <path d="m14 6-6 6 6 6" />
  </svg>
);

export const IconChevronRight = (p: P) => (
  <svg {...base(p)}>
    <path d="m10 6 6 6-6 6" />
  </svg>
);

export const IconArrowRight = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 12h16M14 6l6 6-6 6" />
  </svg>
);

export const IconUpload = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 15V4M8 8l4-4 4 4M4 17v3h16v-3" />
  </svg>
);

export const IconExternal = (p: P) => (
  <svg {...base(p)}>
    <path d="M14 4h6v6M20 4 11 13M9 5H5v14h14v-4" />
  </svg>
);

export const IconClock = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3.5 2" />
  </svg>
);

export const IconTarget = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
  </svg>
);

export const IconLayers = (p: P) => (
  <svg {...base(p)}>
    <path d="m12 3 9 5-9 5-9-5zM3 13l9 5 9-5" />
  </svg>
);

export const IconFilter = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 5h18l-7 8v6l-4-2v-4z" />
  </svg>
);

export const IconRefresh = (p: P) => (
  <svg {...base(p)}>
    <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4" />
  </svg>
);

export const IconMenu = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const IconLogout = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 4H5v16h4M14 8l4 4-4 4M8 12h10" />
  </svg>
);

export const IconWell = (p: P) => (
  <svg {...base(p)}>
    <ellipse cx="12" cy="14" rx="8" ry="4" />
    <ellipse cx="12" cy="13.4" rx="5" ry="2.4" />
    <path d="M4 14v2.5c0 2.2 3.6 4 8 4s8-1.8 8-4V14" />
  </svg>
);

export const IconPole = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3v18M6 6h12M8 6c0 2 8 2 8 0M7 21h10" />
  </svg>
);

export const IconCabinet = (p: P) => (
  <svg {...base(p)}>
    <rect x="6" y="3" width="12" height="18" rx="1" />
    <path d="M12 3v18M14.8 10v3" />
  </svg>
);

export const IconCable = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 7c6 6 12 6 18 0M3 13c6 6 12 6 18 0" />
  </svg>
);

export const assetTypeIcon = (type: string | null | undefined) => {
  switch (type) {
    case 'telecom_well':
      return IconWell;
    case 'pole':
      return IconPole;
    case 'telecom_cabinet':
      return IconCabinet;
    case 'cable_line':
      return IconCable;
    default:
      return IconAsset;
  }
};