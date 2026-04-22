import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface EChartProps {
  option: echarts.EChartsOption;
  className?: string;
  onClick?: (params: unknown) => void;
}

export function EChart({ option, className, onClick }: EChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const instance = echarts.init(containerRef.current);
    instanceRef.current = instance;
    instance.setOption(option);
    instance.resize();

    const resizeHandler = () => instance.resize();
    window.addEventListener('resize', resizeHandler);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(containerRef.current);

    return () => {
      window.removeEventListener('resize', resizeHandler);
      observer.disconnect();
      instance.dispose();
      instanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    instanceRef.current?.setOption(option, true);
  }, [option]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !onClick) {
      return;
    }

    const clickHandler = (params: unknown) => {
      onClick(params);
    };
    instance.on('click', clickHandler);

    return () => {
      instance.off('click', clickHandler);
    };
  }, [onClick]);

  return <div ref={containerRef} className={className ?? 'chart'} />;
}
