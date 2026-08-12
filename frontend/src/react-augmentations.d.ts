// @types/react (18.3) predates the `inert` DOM attribute landing in React's own JSX
// typings — it's a real, well-supported HTML attribute (Chrome/Firefox/Safari all
// current), just not yet reflected here. The leading `import` makes this file a module,
// so the block below augments react's types instead of replacing them.
import "react";

declare module "react" {
  interface HTMLAttributes<T> {
    inert?: boolean;
  }
}
