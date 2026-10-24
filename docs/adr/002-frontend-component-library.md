# ADR 002: Frontend Component Library

## Status

Accepted

## Context

OCMP needs a React component library that provides:
- Accessible, WCAG 2.2 AA compliant components
- Responsive design support
- Dark/light theme support
- Form handling
- Data tables, trees, and complex inputs
- Good developer experience

The project brief suggests either Mantine or shadcn/ui (built on Radix).

## Decision

We will use **Mantine v7** as the primary component library.

## Rationale

1. **Batteries included**: Mantine provides a complete set of components out of the box, reducing time to build the UI
2. **Accessibility**: Built with accessibility in mind, meeting WCAG 2.2 AA requirements
3. **Form handling**: @mantine/form provides excellent form state management
4. **Hooks library**: @mantine/hooks provides useful utilities (useDisclosure, useLocalStorage, etc.)
5. **Theming**: Robust theming system with CSS variables, easy dark mode
6. **Documentation**: Excellent documentation with examples
7. **Active maintenance**: Regular updates and responsive maintainers

## Trade-offs

- Larger bundle size than shadcn/ui (mitigated by tree-shaking)
- Less flexibility for custom designs (acceptable for an admin-focused tool)
- Opinionated styling (consistent look is a benefit for our use case)

## Consequences

- Use Mantine components throughout the application
- Follow Mantine's theming conventions
- Use @mantine/form for all forms
- Use @mantine/notifications for toast messages
- PostCSS configuration required for Mantine
