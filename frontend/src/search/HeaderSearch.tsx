import { useState, type FormEvent } from 'react';
import { ActionIcon, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { fetchProgrammes, queryKeys } from '../api/endpoints';
import { defaultVersionId, rememberedVersion } from '../curriculum/currentVersion';
import classes from './HeaderSearch.module.css';

/** The search box of the header. It opens the search page for the version being viewed (or the
 * one last opened); the page does the work. The versions are fetched only when a search is made,
 * so the box costs nothing on the other pages. */
export function HeaderSearch({ versionId }: { versionId?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [text, setText] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const query = text.trim();
    if (query.length < 2) return;
    let version = versionId ?? null;
    if (!version) {
      try {
        const programmes = await queryClient.fetchQuery({
          queryKey: queryKeys.programmes,
          queryFn: fetchProgrammes,
        });
        version = defaultVersionId(programmes, rememberedVersion());
      } catch {
        // Without the list the page chooses the version itself.
      }
    }
    const params = new URLSearchParams({ q: query });
    if (version) params.set('version', version);
    navigate(`/search?${params.toString()}`);
    setText('');
  };

  return (
    <form role="search" onSubmit={submit} className={classes.form}>
      <TextInput
        aria-label={t('search.headerLabel')}
        placeholder={t('search.headerPlaceholder')}
        value={text}
        onChange={(event) => setText(event.currentTarget.value)}
        maxLength={200}
        size="md"
        rightSection={
          <ActionIcon
            type="submit"
            variant="subtle"
            size={36}
            aria-label={t('search.headerSubmit')}
          >
            <IconSearch size={18} aria-hidden />
          </ActionIcon>
        }
        rightSectionPointerEvents="all"
      />
    </form>
  );
}
