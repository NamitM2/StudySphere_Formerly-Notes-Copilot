// web/src/components/LoadingLogo.jsx
// Reusable animated logo loading spinner

export default function LoadingLogo({ size = "md" }) {
  const sizes = {
    xs: { width: 16, height: 16, ringRadius: 5, ringStroke: 1.5, dotRadius: 1.5 },
    sm: { width: 20, height: 20, ringRadius: 7, ringStroke: 2, dotRadius: 2 },
    md: { width: 40, height: 40, ringRadius: 14, ringStroke: 3, dotRadius: 4 },
    lg: { width: 60, height: 60, ringRadius: 20, ringStroke: 4, dotRadius: 6 }
  };

  const { width, height, ringRadius, ringStroke, dotRadius } = sizes[size];
  const center = width / 2;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        {/* Amber Ring */}
        <linearGradient id={`ringGradient-${size}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{stopColor: '#f59e0b', stopOpacity: 1}} />
          <stop offset="50%" style={{stopColor: '#fbbf24', stopOpacity: 1}} />
          <stop offset="100%" style={{stopColor: '#fcd34d', stopOpacity: 1}} />
        </linearGradient>

        {/* Pink dots */}
        <linearGradient id={`orbGradient-${size}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{stopColor: '#f472b6', stopOpacity: 1}} />
          <stop offset="100%" style={{stopColor: '#f472b6', stopOpacity: 1}} />
        </linearGradient>
      </defs>

      {/* Main circular ring */}
      <circle cx={center} cy={center} r={ringRadius} fill="none" stroke={`url(#ringGradient-${size})`} strokeWidth={ringStroke} opacity="0.8"/>

      {/* Orbiting circles - 5 pink dots */}
      <g>
        {/* Circle 1: Fast clockwise (3.2s) */}
        <circle r={dotRadius} fill={`url(#orbGradient-${size})`} opacity="0.9">
          <animateMotion
            dur="3.2s"
            repeatCount="indefinite"
            path={`M ${center + ringRadius},${center} A ${ringRadius},${ringRadius} 0 1,1 ${center + ringRadius},${center - 0.1} Z`}/>
        </circle>

        {/* Circle 2: Slow counter-clockwise (4.8s) */}
        <circle r={dotRadius} fill={`url(#orbGradient-${size})`} opacity="0.9">
          <animateMotion
            dur="4.8s"
            repeatCount="indefinite"
            begin="-1.8s"
            path={`M ${center + ringRadius},${center} A ${ringRadius},${ringRadius} 0 1,0 ${center + ringRadius},${center + 0.1} Z`}/>
        </circle>

        {/* Circle 3: Medium clockwise (4.1s) */}
        <circle r={dotRadius} fill={`url(#orbGradient-${size})`} opacity="0.9">
          <animateMotion
            dur="4.1s"
            repeatCount="indefinite"
            begin="-3.2s"
            path={`M ${center + ringRadius},${center} A ${ringRadius},${ringRadius} 0 1,1 ${center + ringRadius},${center - 0.1} Z`}/>
        </circle>

        {/* Circle 4: Fast counter-clockwise (3.5s) */}
        <circle r={dotRadius} fill={`url(#orbGradient-${size})`} opacity="0.9">
          <animateMotion
            dur="3.5s"
            repeatCount="indefinite"
            begin="-0.7s"
            path={`M ${center + ringRadius},${center} A ${ringRadius},${ringRadius} 0 1,0 ${center + ringRadius},${center + 0.1} Z`}/>
        </circle>

        {/* Circle 5: Medium-slow clockwise (4.6s) */}
        <circle r={dotRadius} fill={`url(#orbGradient-${size})`} opacity="0.9">
          <animateMotion
            dur="4.6s"
            repeatCount="indefinite"
            begin="-2.3s"
            path={`M ${center + ringRadius},${center} A ${ringRadius},${ringRadius} 0 1,1 ${center + ringRadius},${center - 0.1} Z`}/>
        </circle>
      </g>
    </svg>
  );
}
