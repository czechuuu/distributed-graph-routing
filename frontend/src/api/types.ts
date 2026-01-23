export type Coordinate = {
  lat: number
  lng: number
}

export type NodeRef = {
  node_id: string
  lat: number
  lng: number
}

export type Segment = {
  u: NodeRef
  v: NodeRef
  expandable: boolean
}

export type ExpandedSegment = {
  u: NodeRef
  v: NodeRef
  polyline: Coordinate[]
}

export type RouteSummary = {
  segments_count: number
  distance_m: number
}

export type RouteResponse = {
  path_found: boolean
  segments: Segment[]
  summary: RouteSummary
}

export type RouteRequest = {
  start: Coordinate
  end: Coordinate
}

export type RouteExpandRequest = {
  segments: Array<Pick<Segment, 'u' | 'v'>>
}

export type RouteExpandError = {
  index: number
  error: string
}

export type RouteExpandResponse = {
  expanded: ExpandedSegment[]
  errors: RouteExpandError[]
}
