#!/usr/bin/env python3
"""
Script to update app.py with watermark, banner, and maintain softer gray theme.
"""

import re

def update_app_py():
    app_path = r'c:\Users\mkvau\OneDrive\Documents\Sales\Python\FunnelForge\funnel_forge\app.py'

    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add image loading in __init__ after line 600 (after minsize)
    # Find the position after self.minsize(980, 620)
    init_pattern = r'(self\.minsize\(980, 620\))\n'
    init_replacement = r'''\1

        # NEW: Load watermark and banner images once at startup
        try:
            watermark_path = resource_path("assets", "fnnl_forge_watermark.png")
            watermark_img = Image.open(watermark_path)
            # Store original for later resizing
            self.watermark_original = watermark_img
            self.watermark_photo = None  # Will be created when we know canvas size
        except Exception as e:
            print(f"Could not load watermark: {e}")
            self.watermark_original = None
            self.watermark_photo = None

        try:
            banner_path = resource_path("assets", "fnnl_forge_banner.png")
            banner_img = Image.open(banner_path)
            # Resize banner to fit window width (e.g., 1180px wide, maintain aspect ratio)
            banner_height = int((banner_img.height / banner_img.width) * 1180)
            banner_resized = banner_img.resize((1180, banner_height), RESAMPLE_LANCZOS)
            self.banner_photo = ImageTk.PhotoImage(banner_resized)
        except Exception as e:
            print(f"Could not load banner: {e}")
            self.banner_photo = None

'''

    if re.search(init_pattern, content):
        content = re.sub(init_pattern, init_replacement, content, count=1)

    # 2. Replace _build_header to add banner image instead of text header
    # Find the entire _build_header method and replace it
    header_pattern = r'    def _build_header\(self\):.*?(?=    def _build_nav_and_content\(self\):)'

    header_replacement = '''    def _build_header(self):
        """Build top banner with image"""
        # NEW: top banner image
        if self.banner_photo:
            # Create banner frame at the very top
            banner_frame = tk.Frame(self, bg=BG_ROOT)
            banner_frame.pack(fill="x", side="top")

            banner_label = tk.Label(
                banner_frame,
                image=self.banner_photo,
                bg=BG_ROOT,
                borderwidth=0
            )
            banner_label.pack()
        else:
            # Fallback: minimal header if banner image not found
            header = tk.Frame(self, bg=BG_HEADER, height=70)
            header.pack(fill="x", side="top")
            header.pack_propagate(False)

            left_section = tk.Frame(header, bg=BG_HEADER)
            left_section.pack(side="left", padx=24, pady=16)

            tk.Label(
                left_section,
                text="FUNNEL FORGE",
                bg=BG_HEADER,
                fg=FG_WHITE,
                font=("Segoe UI", 18, "bold"),
            ).pack(side="left")

    '''

    if re.search(header_pattern, content, re.DOTALL):
        content = re.sub(header_pattern, header_replacement, content, count=1, flags=re.DOTALL)

    # 3. Add watermark to main content area in _build_nav_and_content
    # Find where content_stack is created and add watermark canvas
    nav_pattern = r'(        # Content stack\n        content_stack = tk\.Frame\(shell, bg=BG_ROOT\)\n        content_stack\.grid\(row=0, column=1, sticky="nsew"\)\n        content_stack\.rowconfigure\(0, weight=1\)\n        content_stack\.columnconfigure\(0, weight=1\))\n'

    nav_replacement = r'''\1

        # NEW: watermark background - add canvas behind all content
        if self.watermark_original:
            watermark_canvas = tk.Canvas(
                content_stack,
                bg=BG_ROOT,
                highlightthickness=0,
                borderwidth=0
            )
            watermark_canvas.grid(row=0, column=0, sticky="nsew")

            # Function to update watermark on resize
            def update_watermark(event=None):
                try:
                    if not self.watermark_original:
                        return

                    w = watermark_canvas.winfo_width()
                    h = watermark_canvas.winfo_height()

                    if w <= 1 or h <= 1:
                        return

                    # Resize watermark to fit nicely in center (e.g., 40% of canvas size)
                    scale = 0.4
                    wm_width = int(w * scale)
                    wm_height = int((self.watermark_original.height / self.watermark_original.width) * wm_width)

                    watermark_resized = self.watermark_original.resize((wm_width, wm_height), RESAMPLE_LANCZOS)
                    self.watermark_photo = ImageTk.PhotoImage(watermark_resized)

                    # Clear and redraw
                    watermark_canvas.delete("all")
                    watermark_canvas.create_image(
                        w // 2, h // 2,
                        image=self.watermark_photo,
                        anchor="center"
                    )
                except Exception as e:
                    print(f"Error updating watermark: {e}")

            # Bind resize event
            watermark_canvas.bind("<Configure>", update_watermark)

            # Initial draw
            self.after(100, update_watermark)

'''

    if re.search(nav_pattern, content):
        content = re.sub(nav_pattern, nav_replacement, content, count=1)

    # Write updated content
    output_path = r'c:\Users\mkvau\OneDrive\Documents\Sales\Python\FunnelForge\funnel_forge\app_updated.py'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Updated app.py written to: {output_path}")
    print(f"Total size: {len(content)} characters")
    return output_path

if __name__ == "__main__":
    update_app_py()
