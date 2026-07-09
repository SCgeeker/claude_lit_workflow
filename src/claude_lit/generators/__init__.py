"""
生成器模組
支援投影片、筆記等多種格式生成
"""

from .slide_maker import SlideMaker, make_slides

__all__ = ['SlideMaker', 'make_slides']
