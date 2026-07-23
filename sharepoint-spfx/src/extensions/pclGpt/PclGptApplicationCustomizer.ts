import { override } from '@microsoft/decorators';
import {
  BaseApplicationCustomizer,
  PlaceholderContent
} from '@microsoft/sp-application-base';
import { Log } from '@microsoft/sp-core-library';

import * as strings from 'PclGptApplicationCustomizerStrings';

const LOG_SOURCE: string = strings.Title;
const WIDGET_HOST_ID = 'pcl-gpt-spfx-host';
const LOADER_SCRIPT_ID = 'pcl-gpt-loader-script';

export interface IPclGptApplicationCustomizerProperties {
  loaderScriptUrl?: string;
  embedUrl?: string;
  widgetWidth?: number;
  widgetHeight?: number;
  openByDefault?: boolean;
}

export default class PclGptApplicationCustomizer extends BaseApplicationCustomizer<IPclGptApplicationCustomizerProperties> {
  private _placeholder: PlaceholderContent | undefined;

  @override
  public async onInit(): Promise<void> {
    Log.info(LOG_SOURCE, 'Initialized PCL GPT One Desk customizer.');

    this.context.placeholderProvider.changedEvent.add(this, this._render);
    this._render();

    return Promise.resolve();
  }

  @override
  public onDispose(): void {
    this.context.placeholderProvider.changedEvent.remove(this, this._render);
    this._placeholder?.dispose();
    this._placeholder = undefined;

    const loaderScript = document.getElementById(LOADER_SCRIPT_ID);
    if (loaderScript) {
      loaderScript.remove();
    }

    const widgetHost = document.getElementById(WIDGET_HOST_ID);
    if (widgetHost) {
      widgetHost.remove();
    }
  }

  private _render = (): void => {
    if (document.getElementById(LOADER_SCRIPT_ID)) {
      return;
    }

    if (!this._placeholder) {
      this._placeholder = this.context.placeholderProvider.tryCreateContent(
        PlaceholderContent.Bottom,
        { onDispose: this.onDispose.bind(this) }
      );
    }

    const loaderScriptUrl = this.properties.loaderScriptUrl?.trim();
    const embedUrl = this.properties.embedUrl?.trim();

    if (!loaderScriptUrl || !embedUrl) {
      Log.error(
        LOG_SOURCE,
        new Error('Both loaderScriptUrl and embedUrl must be provided.')
      );
      return;
    }

    const host = document.createElement('div');
    host.id = WIDGET_HOST_ID;
    host.setAttribute('data-loader-script-url', loaderScriptUrl);
    host.setAttribute('data-embed-url', embedUrl);

    document.body.appendChild(host);

    const script = document.createElement('script');
    script.id = LOADER_SCRIPT_ID;
    script.src = loaderScriptUrl;
    script.async = true;
    script.dataset.embedUrl = embedUrl;
    script.dataset.width = String(this.properties.widgetWidth ?? 460);
    script.dataset.height = String(this.properties.widgetHeight ?? 720);
    script.dataset.open = String(this.properties.openByDefault ?? true);

    document.body.appendChild(script);
  };
}
