#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "networkx",
# ]
# ///
"""
Generate a visualization showing how the graph is transformed through preprocessing stages.

Timeline:
1. Unprocessed graph (raw road network)
2. Graph with S2 cell boundaries outlined
3. Split view:
   a) Separated shards with internal edges
   b) Overlay graph with shortcuts
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, ConnectionPatch
from matplotlib.lines import Line2D
import networkx as nx
import numpy as np

# Style configuration matching the pipeline diagram
COLORS = {
    'background': '#F5F5F5',
    'card_bg': '#FFFFFF',
    'header': '#2C3E50',
    'text': '#333333',
    'accent': '#17A2B8',
    'edge': '#666666',
    'node': '#2C3E50',
    'shard1': '#E74C3C',  # Red shard
    'shard2': '#3498DB',  # Blue shard
    'shard3': '#27AE60',  # Green shard
    'bridge': '#9B59B6',  # Purple for bridges
    'shortcut': '#F39C12',  # Orange for shortcuts
    'boundary': '#E67E22',  # Boundary nodes
    'grid': '#BDC3C7',
}


def create_sample_graph():
    """Create a sample road network graph spanning multiple 'shards'."""
    G = nx.Graph()
    
    # Define nodes with positions - simulating a road network
    # Organized into 3 shard regions
    nodes = {
        # Shard 1 (top-left region)
        1: (0.8, 2.8), 2: (1.5, 3.2), 3: (2.2, 2.6),
        4: (1.0, 2.0), 5: (1.8, 2.2), 6: (2.5, 1.8),
        
        # Shard 2 (top-right region)  
        7: (3.5, 3.0), 8: (4.2, 2.8), 9: (4.8, 3.2),
        10: (3.8, 2.0), 11: (4.5, 2.2), 12: (3.2, 2.4),
        
        # Shard 3 (bottom region)
        13: (1.5, 0.8), 14: (2.2, 1.0), 15: (3.0, 0.6),
        16: (3.8, 0.8), 17: (2.5, 0.2), 18: (4.2, 1.0),
    }
    
    for node_id, pos in nodes.items():
        G.add_node(node_id, pos=pos)
    
    # Internal edges within shards
    internal_edges = [
        # Shard 1 internal
        (1, 2), (2, 3), (1, 4), (4, 5), (5, 6), (2, 5), (3, 6),
        # Shard 2 internal
        (7, 8), (8, 9), (7, 12), (12, 10), (10, 11), (8, 11), (9, 11),
        # Shard 3 internal
        (13, 14), (14, 15), (15, 16), (16, 18), (14, 17), (15, 17),
    ]
    
    # Bridge edges (cross-shard)
    bridge_edges = [
        (6, 12),   # Shard 1 -> Shard 2
        (3, 7),    # Shard 1 -> Shard 2
        (6, 14),   # Shard 1 -> Shard 3
        (10, 16),  # Shard 2 -> Shard 3
        (11, 18),  # Shard 2 -> Shard 3
    ]
    
    G.add_edges_from(internal_edges, edge_type='internal')
    G.add_edges_from(bridge_edges, edge_type='bridge')
    
    return G, nodes, internal_edges, bridge_edges


def get_shard_assignment(node_id):
    """Assign nodes to shards based on their ID."""
    if node_id <= 6:
        return 1
    elif node_id <= 12:
        return 2
    else:
        return 3


def get_shard_color(shard_id):
    """Get color for a shard."""
    colors = {1: COLORS['shard1'], 2: COLORS['shard2'], 3: COLORS['shard3']}
    return colors.get(shard_id, COLORS['node'])


def get_boundary_nodes(bridge_edges):
    """Identify boundary nodes (nodes that have bridge edges)."""
    boundary = set()
    for u, v in bridge_edges:
        boundary.add(u)
        boundary.add(v)
    return boundary


def draw_graph_basic(ax, G, nodes, title, show_labels=True):
    """Draw the basic unprocessed graph."""
    ax.set_facecolor(COLORS['card_bg'])
    
    # Draw edges
    for u, v in G.edges():
        x1, y1 = nodes[u]
        x2, y2 = nodes[v]
        ax.plot([x1, x2], [y1, y2], color=COLORS['edge'], linewidth=1.5, zorder=1)
    
    # Draw nodes
    for node_id, (x, y) in nodes.items():
        ax.scatter(x, y, s=120, c=COLORS['node'], zorder=2, edgecolors='white', linewidths=1.5)
        if show_labels:
            ax.annotate(str(node_id), (x, y), fontsize=7, ha='center', va='center', 
                       color='white', fontweight='bold', zorder=3)
    
    ax.set_title(title, fontsize=11, fontweight='bold', color=COLORS['header'], pad=10)
    ax.set_xlim(0, 5.5)
    ax.set_ylim(-0.3, 3.8)
    ax.set_aspect('equal')
    ax.axis('off')


def draw_graph_with_cells(ax, G, nodes, title):
    """Draw graph with S2 cell boundaries outlined."""
    ax.set_facecolor(COLORS['card_bg'])
    
    # Draw S2 cell boundaries (simplified as rectangles)
    cell_bounds = [
        (0.3, 1.4, 2.5, 2.2),   # Shard 1
        (2.8, 1.4, 2.5, 2.2),   # Shard 2
        (1.0, -0.3, 3.8, 1.5),  # Shard 3
    ]
    cell_labels = ['S2 Cell A', 'S2 Cell B', 'S2 Cell C']
    cell_colors = [COLORS['shard1'], COLORS['shard2'], COLORS['shard3']]
    
    for i, (x, y, w, h) in enumerate(cell_bounds):
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1",
                              facecolor=cell_colors[i], alpha=0.15, 
                              edgecolor=cell_colors[i], linewidth=2, linestyle='--', zorder=0)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h - 0.15, cell_labels[i], fontsize=8, 
               color=cell_colors[i], ha='center', fontweight='bold', alpha=0.8)
    
    # Draw edges
    for u, v in G.edges():
        x1, y1 = nodes[u]
        x2, y2 = nodes[v]
        ax.plot([x1, x2], [y1, y2], color=COLORS['edge'], linewidth=1.5, zorder=1)
    
    # Draw nodes colored by shard
    for node_id, (x, y) in nodes.items():
        shard = get_shard_assignment(node_id)
        color = get_shard_color(shard)
        ax.scatter(x, y, s=120, c=color, zorder=2, edgecolors='white', linewidths=1.5)
        ax.annotate(str(node_id), (x, y), fontsize=7, ha='center', va='center', 
                   color='white', fontweight='bold', zorder=3)
    
    ax.set_title(title, fontsize=11, fontweight='bold', color=COLORS['header'], pad=10)
    ax.set_xlim(0, 5.5)
    ax.set_ylim(-0.3, 3.8)
    ax.set_aspect('equal')
    ax.axis('off')


def draw_separated_shards(ax, nodes, internal_edges, bridge_edges, title):
    """Draw separated shards with only internal edges."""
    ax.set_facecolor(COLORS['card_bg'])
    
    boundary_nodes = get_boundary_nodes(bridge_edges)
    
    # Shard regions with slight separation
    shard_offsets = {1: (-0.3, 0.3), 2: (0.3, 0.3), 3: (0, -0.3)}
    
    # Draw shard backgrounds
    cell_bounds = [
        (0.0, 1.7, 2.5, 2.0),   # Shard 1
        (3.1, 1.7, 2.3, 2.0),   # Shard 2
        (1.0, -0.4, 3.8, 1.5),  # Shard 3
    ]
    cell_colors = [COLORS['shard1'], COLORS['shard2'], COLORS['shard3']]
    shard_labels = ['Shard 1', 'Shard 2', 'Shard 3']
    
    for i, (x, y, w, h) in enumerate(cell_bounds):
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1",
                              facecolor=cell_colors[i], alpha=0.12,
                              edgecolor=cell_colors[i], linewidth=2, zorder=0)
        ax.add_patch(rect)
        ax.text(x + 0.15, y + h - 0.15, shard_labels[i], fontsize=8,
               color=cell_colors[i], ha='left', fontweight='bold')
    
    # Adjusted positions with shard separation
    adjusted_nodes = {}
    for node_id, (x, y) in nodes.items():
        shard = get_shard_assignment(node_id)
        ox, oy = shard_offsets[shard]
        adjusted_nodes[node_id] = (x + ox, y + oy)
    
    # Draw internal edges only
    for u, v in internal_edges:
        x1, y1 = adjusted_nodes[u]
        x2, y2 = adjusted_nodes[v]
        shard = get_shard_assignment(u)
        color = get_shard_color(shard)
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=2, alpha=0.7, zorder=1)
    
    # Draw nodes
    for node_id, (x, y) in adjusted_nodes.items():
        shard = get_shard_assignment(node_id)
        color = get_shard_color(shard)
        
        # Highlight boundary nodes
        if node_id in boundary_nodes:
            ax.scatter(x, y, s=180, c=COLORS['boundary'], zorder=2, 
                      edgecolors='white', linewidths=2, marker='s')
        else:
            ax.scatter(x, y, s=120, c=color, zorder=2, edgecolors='white', linewidths=1.5)
        
        ax.annotate(str(node_id), (x, y), fontsize=7, ha='center', va='center',
                   color='white', fontweight='bold', zorder=3)
    
    ax.set_title(title, fontsize=10, fontweight='bold', color=COLORS['header'], pad=8)
    ax.set_xlim(-0.3, 5.8)
    ax.set_ylim(-0.5, 4.0)
    ax.set_aspect('equal')
    ax.axis('off')


def draw_overlay_graph(ax, nodes, bridge_edges, title):
    """Draw overlay graph with bridges and shortcuts."""
    ax.set_facecolor(COLORS['card_bg'])
    
    boundary_nodes = get_boundary_nodes(bridge_edges)
    
    # Shard offsets (same as separated shards)
    shard_offsets = {1: (-0.3, 0.3), 2: (0.3, 0.3), 3: (0, -0.3)}
    
    # Draw faded shard backgrounds
    cell_bounds = [
        (0.0, 1.7, 2.5, 2.0),
        (3.1, 1.7, 2.3, 2.0),
        (1.0, -0.4, 3.8, 1.5),
    ]
    cell_colors = [COLORS['shard1'], COLORS['shard2'], COLORS['shard3']]
    
    for i, (x, y, w, h) in enumerate(cell_bounds):
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1",
                              facecolor=cell_colors[i], alpha=0.08,
                              edgecolor=cell_colors[i], linewidth=1.5, linestyle=':', zorder=0)
        ax.add_patch(rect)
    
    # Adjusted positions
    adjusted_nodes = {}
    for node_id, (x, y) in nodes.items():
        shard = get_shard_assignment(node_id)
        ox, oy = shard_offsets[shard]
        adjusted_nodes[node_id] = (x + ox, y + oy)
    
    # Define shortcuts (boundary-to-boundary within same shard)
    shortcuts = [
        (3, 6, 1),   # Shard 1 shortcut
        (7, 10, 2), (7, 11, 2), (12, 10, 2), (12, 11, 2),  # Shard 2 shortcuts
        (14, 16, 3), (14, 18, 3),  # Shard 3 shortcuts
    ]
    
    # Draw shortcuts (dashed curves)
    for u, v, shard in shortcuts:
        if u in boundary_nodes and v in boundary_nodes:
            x1, y1 = adjusted_nodes[u]
            x2, y2 = adjusted_nodes[v]
            # Draw curved shortcut
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 + 0.25  # Curve upward
            ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                       arrowprops=dict(arrowstyle='->', color=COLORS['shortcut'],
                                      lw=2, ls='--', connectionstyle='arc3,rad=0.2'),
                       zorder=1)
    
    # Draw bridge edges (solid, prominent)
    for u, v in bridge_edges:
        x1, y1 = adjusted_nodes[u]
        x2, y2 = adjusted_nodes[v]
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                   arrowprops=dict(arrowstyle='->', color=COLORS['bridge'],
                                  lw=2.5, connectionstyle='arc3,rad=0.1'),
                   zorder=2)
    
    # Draw only boundary nodes
    for node_id in boundary_nodes:
        x, y = adjusted_nodes[node_id]
        shard = get_shard_assignment(node_id)
        ax.scatter(x, y, s=180, c=COLORS['boundary'], zorder=3,
                  edgecolors='white', linewidths=2, marker='s')
        ax.annotate(str(node_id), (x, y), fontsize=7, ha='center', va='center',
                   color='white', fontweight='bold', zorder=4)
    
    ax.set_title(title, fontsize=10, fontweight='bold', color=COLORS['header'], pad=8)
    ax.set_xlim(-0.3, 5.8)
    ax.set_ylim(-0.5, 4.0)
    ax.set_aspect('equal')
    ax.axis('off')


def draw_arrow_between_axes(fig, ax_from, ax_to, vertical=False):
    """Draw a connecting arrow between two axes."""
    if vertical:
        # Arrow going down
        arrow = ConnectionPatch(
            xyA=(0.5, 0), xyB=(0.5, 1),
            coordsA='axes fraction', coordsB='axes fraction',
            axesA=ax_from, axesB=ax_to,
            arrowstyle='->', mutation_scale=20,
            color=COLORS['accent'], lw=2.5
        )
    else:
        # Arrow going right
        arrow = ConnectionPatch(
            xyA=(1.02, 0.5), xyB=(-0.02, 0.5),
            coordsA='axes fraction', coordsB='axes fraction',
            axesA=ax_from, axesB=ax_to,
            arrowstyle='->', mutation_scale=20,
            color=COLORS['accent'], lw=2.5
        )
    fig.add_artist(arrow)


def add_legend(ax):
    """Add a legend explaining the visual elements."""
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['node'],
               markersize=10, label='Internal Node'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor=COLORS['boundary'],
               markersize=10, label='Boundary Node'),
        Line2D([0], [0], color=COLORS['bridge'], linewidth=2, label='Bridge Edge'),
        Line2D([0], [0], color=COLORS['shortcut'], linewidth=2, linestyle='--', label='Shortcut'),
    ]
    ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.05),
              ncol=4, frameon=True, fancybox=True, shadow=True, fontsize=9)


def main():
    # Create the sample graph
    G, nodes, internal_edges, bridge_edges = create_sample_graph()
    
    # Create figure with custom layout
    fig = plt.figure(figsize=(16, 10), facecolor=COLORS['background'])
    
    # Create grid spec for layout:
    # Row 1: [Graph 1] -> [Graph 2] -> [Split into Graph 3a/3b]
    gs = fig.add_gridspec(2, 4, width_ratios=[1, 1, 0.1, 1], height_ratios=[1, 1],
                          hspace=0.15, wspace=0.08,
                          left=0.05, right=0.95, top=0.88, bottom=0.12)
    
    # Create axes
    ax1 = fig.add_subplot(gs[:, 0])  # Unprocessed graph (spans both rows)
    ax2 = fig.add_subplot(gs[:, 1])  # Graph with cells (spans both rows)
    ax3a = fig.add_subplot(gs[0, 3])  # Separated shards
    ax3b = fig.add_subplot(gs[1, 3])  # Overlay graph
    
    # Draw each stage
    draw_graph_basic(ax1, G, nodes, "1. Raw Graph\n(Unprocessed)")
    draw_graph_with_cells(ax2, G, nodes, "2. S2 Cell Assignment\n(Geographic Sharding)")
    draw_separated_shards(ax3a, nodes, internal_edges, bridge_edges, 
                         "3a. Shard Graphs\n(Internal Edges Only)")
    draw_overlay_graph(ax3b, nodes, bridge_edges, 
                      "3b. Overlay Graph\n(Bridges + Shortcuts)")
    
    # Add connecting arrows
    draw_arrow_between_axes(fig, ax1, ax2)
    draw_arrow_between_axes(fig, ax2, ax3a)
    draw_arrow_between_axes(fig, ax2, ax3b)
    
    # Add title
    fig.suptitle('Graph Transformation Through Preprocessing Pipeline', 
                fontsize=16, fontweight='bold', color=COLORS['header'], y=0.95)
    
    # Add legend
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['shard1'],
               markersize=10, label='Shard 1 (Cell A)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['shard2'],
               markersize=10, label='Shard 2 (Cell B)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['shard3'],
               markersize=10, label='Shard 3 (Cell C)'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor=COLORS['boundary'],
               markersize=10, label='Boundary Node'),
        Line2D([0], [0], color=COLORS['bridge'], linewidth=2.5, label='Bridge Edge'),
        Line2D([0], [0], color=COLORS['shortcut'], linewidth=2, linestyle='--', label='Shortcut'),
    ]
    fig.legend(handles=legend_elements, loc='lower center', 
              ncol=6, frameon=True, fancybox=True, shadow=True, fontsize=9,
              bbox_to_anchor=(0.5, 0.02))
    
    # Save figure
    output_path = 'graph_transformation_diagram.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=COLORS['background'])
    print(f"Saved diagram to: {output_path}")
    
    plt.close()


if __name__ == '__main__':
    main()
