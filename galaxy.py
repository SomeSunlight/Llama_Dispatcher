import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D

# --- WICHTIG: Backend explizit setzen ---
plt.switch_backend('Qt5Agg')

# --- KONFIGURATION ---
N_PARTICLES = 2000
SPEED = 10
COLOR_MAP = "plasma"

def update(frame):
    # ... (Rest der Funktion bleibt gleich) ...
    ax.clear()
    a = 0.5
    b = 0.5
    theta = np.linspace(0, 4 * np.pi, N_PARTICLES)
    rotation_offset = frame * 0.1
    noise = np.random.normal(0, 0.1, N_PARTICLES)
    r = a * np.exp(b * theta) + noise
    x = r * np.cos(theta + rotation_offset)
    y = r * np.sin(theta + rotation_offset)
    z = np.sin(theta + rotation_offset) * 2 + np.random.normal(0, 0.05, N_PARTICLES)
    ax.scatter(x, y, z, c=theta, cmap=COLOR_MAP, s=2, alpha=0.8)
    ax.set_title("Interaktive 3D-Spiral-Galaxie", pad=20, fontname='sans-serif', fontsize=12, color='white')
    ax.set_facecolor('black')
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.grid(False)
    ax.set_axis_off()

# --- SETUP ---
fig = plt.figure(figsize=(8, 6))
ax = fig.add_subplot(111, projection='3d')
ani = FuncAnimation(fig, update, frames=1000, interval=50, blit=False)

print("🚀 Starte Galaxie-Simulation...")
print("🖱️  Klicke auf das Fenster, um es zu minimieren/rotieren (wenn unterstützt).")
print("⌨️  Drücke ESC oder schließe das Fenster, um zu beenden.")

# --- WICHTIG: block=True ---
plt.show(block=True)
