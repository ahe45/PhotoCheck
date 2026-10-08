"""Bounded two-stage paper-edge heuristic; it is not proof of recapture.

A cheap horizontal-edge prefilter precedes line fitting. Detailed fitting needs
three connected paper sides around the face AND contrast across two sides.
Whole-image borders, isolated clothing seams, and hair alone are insufficient.
No further decoding or neural inference is performed.
"""
import cv2
import numpy as np


def detect_recapture(rgb, metrics, criteria):
    h, w = rgb.shape[:2]
    if min(h, w) < 40:
        return {"recapture_candidate": 0, "recapture_suspected": 0}
    scale = min(1, 384 / max(h, w))
    small = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    center = metrics["face_center_x"] * w
    left_face = center - metrics["face_width_ratio"] * w / 2
    right_face = center + metrics["face_width_ratio"] * w / 2
    forehead = metrics["forehead_y_ratio"] * h
    chin = metrics["chin_y_ratio"] * h
    # A paper top must lie beyond the face and away from the image boundary.
    top_limit = max(0, min(h, int(forehead - .05 * h)))
    edges = cv2.Canny(gray, 5, 15)
    minimum = max(12, round(w * criteria.paper_edge_min))
    horizontal_mask = cv2.morphologyEx(edges, cv2.MORPH_OPEN, np.ones((1, minimum), np.uint8))
    if top_limit < 1 or not np.any(np.count_nonzero(horizontal_mask[max(2, round(h * .02)):top_limit], axis=1) >= minimum):
        return {"recapture_candidate": 0, "recapture_suspected": 0}
    info = {"recapture_candidate": 1, "recapture_suspected": 0}
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, max(12, minimum - 4),
                            minLineLength=minimum, maxLineGap=max(3, round(w * .07)))
    if lines is None:
        return info
    horizontal, vertical = [], []
    for raw in lines.reshape(-1, 4):
        x1, y1, x2, y2 = map(float, raw)
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dx and dy / dx <= .12:
            horizontal.append((min(x1, x2), max(x1, x2), (y1 + y2) / 2))
        elif dy and dx / dy <= .12:
            vertical.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
    # Limit candidate combinations as well as image size; highly textured files
    # cannot make line fitting grow without bound.
    tops = sorted((line for line in horizontal if .02 * h < line[2] < top_limit
                   and line[0] < left_face and line[1] > right_face), key=lambda l: l[1]-l[0], reverse=True)[:8]
    bottoms = sorted((line for line in horizontal if chin + .04 * h < line[2] < .98 * h),
                     key=lambda l: l[1]-l[0], reverse=True)[:12]
    sides = sorted((line for line in vertical if .02 * w < line[0] < .98 * w
                    and (line[0] < left_face or line[0] > right_face)), key=lambda l: l[2]-l[1], reverse=True)[:12]
    for tx1, tx2, top in tops:
        for side, sy1, sy2 in sides:
            # The line junction must be supported, not just parallel somewhere.
            side_left = side < left_face
            if abs(side - (tx1 if side_left else tx2)) > .08 * w or abs(sy1 - top) > .08 * h:
                continue
            for bx1, bx2, bottom in bottoms:
                if abs(sy2 - bottom) > .08 * h or not bx1 - .08*w <= side <= bx2 + .08*w:
                    continue
                x1, x2 = (side, tx2) if side_left else (tx1, side)
                pw, ph = x2 - x1, bottom - top
                if pw <= 0 or ph <= 0:
                    continue
                area = pw * ph / (w*h)
                if not criteria.paper_area_min <= area <= criteria.paper_area_max or not .45 <= pw/ph <= 1.15:
                    continue
                if not .02*w < x1 < left_face < right_face < x2 < .98*w or not top < forehead < chin < bottom:
                    continue
                if min(bx2, x2) - max(bx1, x1) < pw * .40:
                    continue
                # Median narrow strips ignore the face and reject single noisy
                # pixels. Use the paper top and the supported vertical side.
                gap = max(2, round(min(w, h) * .025))
                xl, xr = round(x1+pw*.15), round(x2-pw*.15)
                yt, yb = round(top+ph*.15), round(bottom-ph*.15)
                t, b, s = round(top), round(bottom), round(side)
                strips = [(small[max(0,t-2*gap):max(0,t-gap),xl:xr], small[t+gap:t+2*gap,xl:xr])]
                if side_left:
                    strips.append((small[yt:yb,max(0,s-2*gap):max(0,s-gap)], small[yt:yb,s+gap:s+2*gap]))
                else:
                    strips.append((small[yt:yb,s+gap:min(w,s+2*gap)], small[yt:yb,max(0,s-2*gap):max(0,s-gap)]))
                if any(a.size == 0 or z.size == 0 for a,z in strips):
                    continue
                contrast = [float(np.max(np.abs(np.median(a,axis=(0,1))-np.median(z,axis=(0,1))))) for a,z in strips]
                if min(contrast) < criteria.paper_contrast_min:
                    continue
                # Uniform digital frames/studio templates are not sufficient.
                # Robust background tone spread requires a substantial outside
                # region; ignore a few extreme pixels and lower captions.
                outside = gray[2:max(2,t-gap),2:-2]
                if outside.size < w*3:
                    continue
                p10,p90 = np.quantile(outside,(.1,.9))
                background = float(p90-p10)
                if background < criteria.paper_background_min:
                    continue
                return dict(info, recapture_suspected=1, paper_area_ratio=round(area,6),
                            paper_top_contrast=round(contrast[0],2), paper_side_contrast=round(contrast[1],2),
                            paper_background_spread=round(background,2),
                            paper_left=round(x1/w,6), paper_top=round(top/h,6),
                            paper_right=round(x2/w,6), paper_bottom=round(bottom/h,6))
    return info
