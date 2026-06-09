import type { ComponentType } from 'react'
import EChartsImport from 'echarts-for-react/esm/core'

const LabEChartsCore = (
  typeof EChartsImport === 'function'
    ? EChartsImport
    : (EChartsImport as { default: ComponentType<Record<string, unknown>> }).default
) as ComponentType<Record<string, unknown>>

export default LabEChartsCore
