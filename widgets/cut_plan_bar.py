from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QWidget


class CutPlanBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._board_length_mm = 0.0
        self._bad_segments_mm = []
        self._hover_segment = None
        self.setMinimumHeight(144)
        self.setMaximumHeight(172)
        self.setMouseTracking(True)
        self._hover_label = QLabel(self)
        self._hover_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._hover_label.setStyleSheet(
            "background: transparent; border: none; font-weight: 600; padding: 0;"
        )
        self._hover_label.hide()

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
        painter.drawText(
            title_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            "Plan ciecia  |  czerwone: odrzut  |  zolte: ciecie",
        )

        bar_rect = QRectF(rect.left(), rect.top() + 52, rect.width(), 22)
        self._draw_base_bar(painter, bar_rect)
        self._draw_bad_segments(painter, bar_rect)
        self._draw_hover_segment(painter, bar_rect)
        self._draw_cut_markers(painter, bar_rect)
        self._draw_scale(painter, bar_rect)

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

    def _draw_hover_segment(self, painter, bar_rect):
        if self._hover_segment is None:
            return
        start_mm, end_mm, is_bad_segment = self._hover_segment
        x1 = self._mm_to_x(end_mm, bar_rect)
        x2 = self._mm_to_x(start_mm, bar_rect)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ff8787") if is_bad_segment else QColor("#69db7c"))
        painter.drawRect(QRectF(x1, bar_rect.top(), max(2.0, x2 - x1), bar_rect.height()))

    def _draw_cut_markers(self, painter, bar_rect):
        cut_positions = sorted(
            {
                float(position)
                for segment in self._bad_segments_mm
                for position in segment
                if 0.0 < float(position) < self._board_length_mm
            }
        )
        if not cut_positions:
            return

        marker_pen = QPen(QColor("#ffd43b"), 2)
        painter.setPen(marker_pen)
        for position_mm in cut_positions:
            x = self._mm_to_x(position_mm, bar_rect)
            painter.drawLine(QPointF(x, bar_rect.top() - 7), QPointF(x, bar_rect.bottom() + 7))
            painter.setBrush(QColor("#ffd43b"))
            painter.drawEllipse(QPointF(x, bar_rect.center().y()), 3.5, 3.5)

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

    def _mm_to_x(self, position_mm, bar_rect):
        if self._board_length_mm <= 0:
            return bar_rect.right()
        ratio = max(0.0, min(1.0, float(position_mm) / self._board_length_mm))
        return bar_rect.right() - bar_rect.width() * ratio

    def mouseMoveEvent(self, event):
        bar_rect = QRectF(self.rect().adjusted(8, 8, -8, -8))
        bar_rect.setTop(bar_rect.top() + 52)
        bar_rect.setHeight(22)
        if self._board_length_mm <= 0 or not bar_rect.contains(event.position()):
            self._clear_hover_segment()
            super().mouseMoveEvent(event)
            return

        ratio = (bar_rect.right() - event.position().x()) / max(1.0, bar_rect.width())
        position_mm = max(0.0, min(self._board_length_mm, ratio * self._board_length_mm))
        start_mm, end_mm, is_bad_segment = self._segment_at(position_mm)
        segment_type = "Odrzut" if is_bad_segment else "Odcinek dobry"
        self._set_hover_segment(
            start_mm, end_mm, is_bad_segment, segment_type, event.position().x()
        )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._clear_hover_segment()
        super().leaveEvent(event)

    def _set_hover_segment(self, start_mm, end_mm, is_bad_segment, segment_type, anchor_x):
        segment = (start_mm, end_mm, is_bad_segment)
        if self._hover_segment != segment:
            self._hover_segment = segment
            self.update()
        self._hover_label.setText(f"{segment_type}: {end_mm - start_mm:.0f} mm")
        self._hover_label.setStyleSheet(
            "background: transparent; border: none; font-weight: 600; padding: 0; "
            f"color: {'#ff8787' if is_bad_segment else '#69db7c'};"
        )
        self._hover_label.adjustSize()
        x = max(
            8,
            min(
                self.width() - self._hover_label.width() - 8,
                int(anchor_x - self._hover_label.width() / 2),
            ),
        )
        self._hover_label.move(x, 30)
        self._hover_label.show()

    def _clear_hover_segment(self):
        if self._hover_segment is not None:
            self._hover_segment = None
            self.update()
        self._hover_label.hide()

    def _segment_at(self, position_mm):
        segments = sorted(
            (
                max(0.0, float(start_mm)),
                min(self._board_length_mm, float(end_mm)),
            )
            for start_mm, end_mm in self._bad_segments_mm
        )
        for start_mm, end_mm in segments:
            if start_mm <= position_mm <= end_mm:
                return start_mm, end_mm, True

        boundaries = [0.0, self._board_length_mm]
        for start_mm, end_mm in segments:
            boundaries.extend((start_mm, end_mm))
        boundaries = sorted(set(boundaries))
        for start_mm, end_mm in zip(boundaries, boundaries[1:]):
            if start_mm <= position_mm <= end_mm:
                return start_mm, end_mm, False
        return 0.0, self._board_length_mm, False
