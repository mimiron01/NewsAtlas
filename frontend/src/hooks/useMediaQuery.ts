import { useEffect, useState } from "react";

/** Tracks a CSS media query in JS, for the rare case a component's behavior (not just
 *  its styling) needs to change at a breakpoint — e.g. whether collapsed nav links
 *  should be removed from tab order. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handleChange = () => setMatches(mql.matches);
    handleChange();
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, [query]);

  return matches;
}
