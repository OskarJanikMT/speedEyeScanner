from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget


class CutPlanBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._board_length_mm = 0.0
        self._bad_segments_mm = []
        self.setMinimumHeight(92)
        self.setMaximumHeight(116)

    def clear_plan(self):
        self._board_length_mm = 0.0
        self._bad_segments_mm = []
        self.update()

    def set_plan(self, board_length_mm, bad_segments_mm):
        try:
            self._board_length_mm = max(0.0, float(board_length_mm))
        except (TypeError, ValueError):
            self._board_length_mm = 0.0
        self._bad_segments_mm = list(bad_segments_mm or [])
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor("#11161b"))

        if self._board_length_mm <= 0:
            painter.setPen(QColor("#8a98a6"))
            painter.drawText(rect, Qt.AlignCenter, "Plan ciecia pojawi sie po analizie AI")
            return

        title_rect = QRectF(rect.left(), rect.top(), rect.width(), 18)
        painter.setPen(QColor("#d8e1ea"))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, "Plan ciecia")

        bar_rect = QRectF(rect.left(), rect.top() + 24, rect.width(), 22)
        self._draw_base_bar(painter, bar_rect)
        self._draw_bad_segments(painter, bar_rect)
        self._draw_scale(painter, bar_rect)
        self._draw_segment_labels(painter, bar_rect)

    def _draw_base_bar(self, painter, bar_rect):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2f9e44"))
        painter.drawRect(bar_rect)

    def _draw_bad_segments(self, painter, bar_rect):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#d94841"))
        for start_mm, end_mm in self._bad_segments_mm:
            if end_mm <= start_mm:
                continue
            x1 = self._mm_to_x(end_mm, bar_rect)
            x2 = self._mm_to_x(start_mm, bar_rect)
            segment_rect = QRectF(x1, bar_rect.top(), max(2.0, x2 - x1), bar_rect.height())
            painter.drawRect(segment_rect)

    def _draw_scale(self, painter, bar_rect):
        scale_top = bar_rect.bottom() + 8
        text_rect = QRectF(bar_rect.left(), scale_top, bar_rect.width(), 16)
        painter.setPen(QColor("#9eb0bf"))
        painter.drawText(
            text_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{int(round(self._board_length_mm))} mm",
        )
        painter.drawText(
            text_rect,
            Qt.AlignHCenter | Qt.AlignVCenter,
            f"{int(round(self._board_length_mm / 2.0))} mm",
        )
        painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, "0 mm")

        painter.setPen(QPen(QColor("#6c7a86"), 1))
        for ratio in (0.0, 0.5, 1.0):
            x = bar_rect.left() + bar_rect.width() * ratio
            painter.drawLine(QPointF(x, bar_rect.bottom()), QPointF(x, bar_rect.bottom() + 6))

    def _draw_segment_labels(self, painter, bar_rect):
        if not self._bad_segments_mm:
            painter.setPen(QColor("#8fd19e"))
            info_rect = QRectF(bar_rect.left(), bar_rect.bottom() + 26, bar_rect.width(), 16)
            painter.drawText(info_rect, Qt.AlignLeft | Qt.AlignVCenter, "Cala deska: dobry material")
            return

        painter.setPen(QColor("#f1b0ab"))
        metrics = QFontMetrics(painter.font())
        base_label_top = bar_rect.bottom() + 26
        max_labels = 6
        row_count = 3
        row_right_edges = [bar_rect.left() - 1 for _ in range(row_count)]

        for index, (start_mm, end_mm) in enumerate(self._bad_segments_mm[:max_labels]):
            label = f"{int(round(start_mm))}-{int(round(end_mm))}"
            label_width = metrics.horizontalAdvance(label) + 10
            segment_left = self._mm_to_x(end_mm, bar_rect)
            segment_right = self._mm_to_x(start_mm, bar_rect)
            anchor_x = (segment_left + segment_right) / 2.0
            preferred_left = max(
                bar_rect.left(),
                min(bar_rect.right() - label_width, anchor_x - label_width / 2.0),
            )

            best_row_index = 0
            best_left = preferred_left
            best_cost = None
            for row_index in range(row_count):
                candidate_left = max(preferred_left, row_right_edges[row_index] + 8)
                candidate_left = min(candidate_left, bar_rect.right() - label_width)
                if candidate_left < bar_rect.left():
                    candidate_left = bar_rect.left()
                overlap_penalty = max(0.0, (row_right_edges[row_index] + 8) - preferred_left)
                distance_penalty = abs(candidate_left - preferred_left)
                row_penalty = row_index * 12.0
                cost = overlap_penalty * 3.0 + distance_penalty + row_penalty
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_row_index = row_index
                    best_left = candidate_left

            row_right_edges[best_row_index] = best_left + label_width
            label_rect = QRectF(
                best_left,
                base_label_top + best_row_index * 16,
                label_width,
                14,
            )
            painter.drawText(label_rect, Qt.AlignCenter, label)

    def _mm_to_x(self, position_mm, bar_rect):
        if self._board_length_mm <= 0:
            return bar_rect.right()
        ratio = max(0.0, min(1.0, float(position_mm) / self._board_length_mm))
        return bar_rect.right() - bar_rect.width() * ratio
