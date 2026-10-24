import {
  ActionIcon,
  AppShell,
  Burger,
  Group,
  Menu,
  NavLink,
  Text,
  Title,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconLogout, IconMoon, IconSun, IconUserCircle } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { NavLink as RouterNavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { logout } from '../api/endpoints';
import { useInstitution } from '../institution/useInstitution';
import { useSession } from '../session/useSession';
import { visibleNavItems } from './navigation';
import classes from './AppLayout.module.css';

function ColorSchemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light', { getInitialValueInEffect: true });
  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label={t('layout.colorScheme')}
      onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
    >
      {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
    </ActionIcon>
  );
}

function UserMenu({ name }: { name: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const signOut = async () => {
    try {
      await logout();
    } finally {
      queryClient.clear();
      navigate('/login', { replace: true });
    }
  };

  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <ActionIcon variant="default" size="lg" aria-label={t('layout.userMenu')}>
          <IconUserCircle size={18} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{t('layout.signedInAs', { name })}</Menu.Label>
        <Menu.Item leftSection={<IconLogout size={16} />} onClick={signOut}>
          {t('layout.signOut')}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

/** The signed-in app frame: header, navigation for the user's permissions, content. */
export function AppLayout() {
  const { t } = useTranslation();
  const [opened, { toggle, close }] = useDisclosure();
  const { data: session } = useSession();
  const institution = useInstitution();
  const location = useLocation();
  const items = visibleNavItems(session?.permissions ?? new Set());

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <a href="#main-content" className={classes.skipLink}>
        {t('layout.skipToContent')}
      </a>
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label={t('layout.toggleNavigation')}
            />
            <Title order={1} size="h4">
              {t('app.shortTitle')}
            </Title>
            {institution && (
              <Text c="dimmed" size="sm" visibleFrom="xs" truncate>
                {institution.name}
              </Text>
            )}
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ColorSchemeToggle />
            {session && <UserMenu name={session.user.display_name} />}
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs" component="nav" aria-label={t('layout.mainNavigation')}>
        {items.map((item) => (
          <NavLink
            key={item.key}
            component={RouterNavLink}
            to={item.path}
            label={t(`nav.${item.key}`)}
            leftSection={<item.icon size={18} stroke={1.6} />}
            active={location.pathname.startsWith(item.path)}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main id="main-content" tabIndex={-1}>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
