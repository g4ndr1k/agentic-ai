export function monthKey(date) {
  return (date || '').slice(0, 7)
}

export function collapseMonthDates(dateList, preferredDates = []) {
  const preferredByMonth = new Map(
    (preferredDates || [])
      .filter(Boolean)
      .map(date => [monthKey(date), date]),
  )

  const firstByMonth = new Map()
  for (const date of dateList || []) {
    const key = monthKey(date)
    if (!key || firstByMonth.has(key)) continue
    firstByMonth.set(key, date)
  }

  return [...firstByMonth.keys()].map(key => preferredByMonth.get(key) || firstByMonth.get(key))
}