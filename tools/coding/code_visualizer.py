import ast
import json
from pyvis.network import Network

class CodeVisualizer:
    def __init__(self):
        self.net = Network(height="600px", width="100%", directed=True)
        
    def analyze_python_file(self, filepath):
        """Parse Python file and create dependency graph"""
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        
        nodes = set()
        edges = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                nodes.add(node.name)
                # Find function calls
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        edges.append((node.name, child.func.id))
        
        # Create interactive graph
        for node in nodes:
            self.net.add_node(node, label=node, color="#00ff88")
        
        for edge in edges:
            self.net.add_edge(edge[0], edge[1], color="#ff4444")
        
        self.net.show("code_graph.html")
        return "code_graph.html"

    def generate_3d_code_city(self, project_structure):
        """Create 3D city visualization where buildings = files"""
        threejs_code = '''
// 3D CODE CITY - Files as buildings, imports as roads
const scene = new THREE.Scene();
const buildings = [];

// Create building for each file
%s.forEach((file, index) => {
    const height = file.lines * 0.1; // Taller buildings for more code
    const geometry = new THREE.BoxGeometry(1, height, 1);
    const material = new THREE.MeshPhongMaterial({ 
        color: file.type === 'python' ? 0x3572A5 : 0xF1E05A 
    });
    const building = new THREE.Mesh(geometry, material);
    building.position.set(index * 2, height / 2, 0);
    buildings.push(building);
    scene.add(building);
});
'''
        return threejs_code