import {
  ActionIcon,
  AppShell,
  Avatar,
  Burger,
  Group,
  Menu,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { IconLogout, IconMoon, IconSun, IconUser } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useNavigate } from 'react-router';

import { logout } from '../api/endpoints';
import { useInstitution } from '../institution/useInstitution';
import { useSession } from '../session/useSession';
import { initials } from './initials';
import { visibleNavItems } from './navigation';
import { Sidebar } from './Sidebar';
import { Wordmark } from './Wordmark';
import classes from './AppLayout.module.css';

function ColorSchemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light', { getInitialValueInEffect: true });
  const next = scheme === 'dark' ? 'light' : 'dark';
  return (
    <ActionIcon
      variant="default"
      size={44}
      aria-label={t(next === 'dark' ? 'layout.toDarkTheme' : 'layout.toLightTheme')}
      onClick={() => setColorScheme(next)}
    >
      {next === 'dark' ? <IconMoon size={20} /> : <IconSun size={20} />}
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
    // No focus placeholder: its role="presentation" + tabindex breaks the menu role's
    // required children (axe aria-required-children); focus starts on the first item.
    <Menu position="bottom-end" withinPortal withInitialFocusPlaceholder={false}>
      <Menu.Target>
        <UnstyledButton
          className={classes.avatarButton}
          aria-label={t('layout.userMenu', { name, initials: initials(name) })}
        >
          <Avatar size={40} radius="xl" color="brand" variant="light" fw={600}>
            {initials(name)}
          </Avatar>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconUser size={16} />} onClick={() => navigate('/account')}>
          {t('layout.account')}
        </Menu.Item>
        <Menu.Item leftSection={<IconLogout size={16} />} onClick={signOut}>
          {t('layout.signOut')}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

/** The signed-in app frame: sidebar with the user's sections, header, content. */
export function AppLayout() {
  const { t } = useTranslation();
  const [opened, { toggle, close }] = useDisclosure();
  const { data: session } = useSession();
  const institution = useInstitution();
  const location = useLocation();
  const items = visibleNavItems(session?.permissions ?? new Set());
  // Below the sm breakpoint (48em) the closed navigation is only moved off-screen;
  // hide it so keyboard and screen-reader users do not reach it either.
  const isPhone = useMediaQuery('(max-width: 47.99em)');
  const navHidden = isPhone === true && !opened;

  return (
    <AppShell
      header={{ height: 73 }}
      navbar={{ width: 232, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding={0}
      // Full-height sidebar from the mockups on wider screens; on phones the header (with
      // the menu button that closes the navigation) stays above the open navigation.
      layout={isPhone ? 'default' : 'alt'}
    >
      <a href="#main-content" className={classes.skipLink}>
        {t('layout.skipToContent')}
      </a>
      <AppShell.Header className={classes.header}>
        <Group h="100%" px={{ base: 'md', sm: 40 }} justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label={t('layout.toggleNavigation')}
              aria-expanded={opened}
              aria-controls="main-navigation"
              className={classes.burger}
            />
            <Group hiddenFrom="sm">
              <Wordmark size="sm" />
            </Group>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <ColorSchemeToggle />
            {session && <UserMenu name={session.user.display_name} />}
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar
        id="main-navigation"
        // Mantine renders a <nav>; the labelled navigation landmark is inside the Sidebar.
        role="none"
        className={classes.navbar}
        withBorder={false}
        data-hidden={navHidden || undefined}
      >
        <AppShell.Section grow>
          <Sidebar
            items={items}
            pathname={location.pathname}
            institutionName={institution?.name}
            onNavigate={close}
          />
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main id="main-content" tabIndex={-1} className={classes.main}>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
