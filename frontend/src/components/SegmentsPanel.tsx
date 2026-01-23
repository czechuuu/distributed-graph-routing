import type { Segment } from '../api/types'

type SegmentsPanelProps = {
  segments: Segment[]
  expandedKeys: Set<string>
  onExpand: (segment: Segment) => void
  isExpanding: Record<string, boolean>
  disabled: boolean
}

function segmentKey(segment: Segment): string {
  return `${segment.u.node_id}-${segment.v.node_id}`
}

export default function SegmentsPanel({
  segments,
  expandedKeys,
  onExpand,
  isExpanding,
  disabled,
}: SegmentsPanelProps) {
  return (
    <section className="panel">
      <h2>Segments</h2>
      {disabled && <div className="muted">Compute a route to list segments.</div>}
      {!disabled && segments.length === 0 && (
        <div className="muted">No segments returned.</div>
      )}
      <ul className="segment-list">
        {segments.map((segment, index) => {
          const key = segmentKey(segment)
          const expanded = expandedKeys.has(key)
          const busy = Boolean(isExpanding[key])
          return (
            <li key={key} className="segment-item">
              <div className="segment-header">
                <span>Segment {index + 1}</span>
                <span className={segment.expandable ? 'badge' : 'badge muted'}>
                  {segment.expandable ? 'expandable' : 'fixed'}
                </span>
              </div>
              <div className="segment-detail">
                <div>
                  <strong>u</strong> {segment.u.lat.toFixed(5)}, {segment.u.lng.toFixed(5)}
                </div>
                <div>
                  <strong>v</strong> {segment.v.lat.toFixed(5)}, {segment.v.lng.toFixed(5)}
                </div>
                <div className="segment-id">
                  {segment.u.node_id} → {segment.v.node_id}
                </div>
              </div>
              <button
                type="button"
                onClick={() => onExpand(segment)}
                disabled={!segment.expandable || expanded || busy}
              >
                {busy ? 'Expanding...' : expanded ? 'Expanded' : 'Expand'}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
