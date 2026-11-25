/* Human wording for machine codes: runtime problems, field errors, import results
 * and notices. Each problem explains what happened and what the user can do. */
(() => {
  'use strict';
  const t = (key, params) => I18n.t(key, params);

  const PROBLEMS = {
    port_in_use: {
      title: 'Local port {port} is already in use',
      hint: 'Stop the program that uses it, or give this service another local port.',
      actions: ['retry', 'edit'],
    },
    port_denied: {
      title: 'Local port {port} needs administrator rights',
      hint: 'Ports below 1024 are privileged. Choose a port of 1024 or higher.',
      actions: ['edit'],
    },
    address_unavailable: {
      title: 'Address {address} does not exist on this machine',
      hint: 'Use 127.0.0.1, localhost or an address of one of your network interfaces.',
      actions: ['edit'],
    },
    port_conflict: {
      title: 'Port {port} is already forwarded by “{detail}”',
      hint: 'Two services cannot listen on the same local port. Stop the other one or change a port.',
      actions: ['edit', 'retry'],
    },
    context_missing: {
      title: 'Context “{context}” is not in your kubeconfig',
      hint: 'Check the context name, or pick one from the list in the editor.',
      actions: ['edit', 'retry'],
    },
    kubeconfig_invalid: {
      title: 'The kubeconfig file could not be loaded',
      hint: 'Check the kubeconfig path in Settings and the file itself.',
      actions: ['settings', 'retry'],
    },
    namespace_missing: {
      title: 'Namespace “{namespace}” was not found',
      hint: 'The namespace may be misspelled or belong to another cluster.',
      actions: ['edit', 'retry'],
    },
    auth: {
      title: 'The cluster rejected your credentials',
      hint: 'Log in again (or renew the certificate or token) and retry.',
      actions: ['retry', 'logs'],
    },
    remote_port_missing: {
      title: 'Remote port {remote} does not exist on {resource}',
      hint: 'Pick one of the ports the resource exposes.',
      actions: ['edit', 'retry'],
    },
    pod_not_ready: {
      title: 'No running pod is ready yet',
      hint: 'The workload may be rolling out or crashing. Bandar keeps trying.',
      actions: ['retry', 'logs'],
    },
    target_missing: {
      title: '{resource} was not found',
      hint: 'Check the resource name and namespace.',
      actions: ['edit', 'retry'],
    },
    invalid_command: {
      title: 'kubectl rejected the command',
      hint: 'Check the extra kubectl flags of this service.',
      actions: ['edit', 'logs'],
    },
    connection_lost: {
      title: 'Lost connection to the pod',
      hint: 'The tunnel dropped (network change, sleep or pod restart). Reconnecting automatically.',
      actions: ['retry', 'logs'],
    },
    api_unreachable: {
      title: 'Cannot reach the cluster',
      hint: 'Check your network or VPN. Bandar retries automatically.',
      actions: ['retry', 'logs'],
    },
    start_timeout: {
      title: 'kubectl did not become ready in time',
      hint: 'The cluster may be slow. You can raise the start timeout in Settings.',
      actions: ['retry', 'logs'],
    },
    listener_lost: {
      title: 'The local listener stopped answering',
      hint: 'The health check found the port closed. Reconnecting.',
      actions: ['retry', 'logs'],
    },
    kubectl_missing: {
      title: 'kubectl could not be started',
      hint: 'Install kubectl or set its full path in Settings.',
      actions: ['settings', 'retry'],
    },
    exited: {
      title: 'kubectl exited unexpectedly',
      hint: 'See the logs for details.',
      actions: ['retry', 'logs'],
    },
    timeout: { title: 'kubectl timed out', hint: '', actions: ['retry'] },
    unknown: {
      title: 'kubectl reported an error',
      hint: 'See the logs for the full output.',
      actions: ['retry', 'logs'],
    },
    remote_refused: {
      title: 'The application in the pod refused a connection',
      hint: 'The tunnel works, but nothing listens on remote port {remote} inside the pod.',
      actions: ['logs', 'dismiss'],
    },
    connection_failed: {
      title: 'A connection through the tunnel failed',
      hint: 'Other connections may still work. See the logs.',
      actions: ['logs', 'dismiss'],
    },
  };

  function ownerText(owner) {
    if (!owner) return '';
    if (!owner.pid) return t('another user or a system service');
    if (owner.outgoing) return t('an outgoing connection of {name} (PID {pid})', { name: owner.name || '?', pid: owner.pid });
    if (owner.ours) return t('a leftover kubectl port-forward (PID {pid})', { pid: owner.pid });
    return t('{name} (PID {pid})', { name: owner.name || '?', pid: owner.pid });
  }

  function resourceText(service) {
    const prefix = { service: 'svc', pod: 'pod', deployment: 'deploy', statefulset: 'sts', replicaset: 'rs' };
    return `${prefix[service.kind] || service.kind}/${service.target}`;
  }

  /** Everything the interface shows about a problem: title, hint, detail and actions. */
  function problem(error, service, resolved = {}) {
    const spec = PROBLEMS[error.code] || PROBLEMS.unknown;
    const params = {
      port: service.localPort,
      remote: service.remotePort,
      address: service.address,
      resource: resourceText(service),
      context: resolved.context || service.context,
      namespace: resolved.namespace || service.namespace,
      detail: error.detail,
    };
    let hint = t(spec.hint, params);
    let actions = [...spec.actions];
    if (error.code === 'port_in_use' && error.owner) {
      hint = `${t('Used by {owner}.', { owner: ownerText(error.owner) })} ${hint}`;
      if (error.owner.ours) actions = ['free', ...actions];
    }
    return { code: error.code, title: t(spec.title, params), hint, detail: error.detail || '', actions };
  }

  const FIELD = {
    required: 'This field is required.',
    duplicate_service: 'Another service already has this name.',
    duplicate_group: 'Another group already has this name.',
    missing_group: 'The selected group no longer exists.',
    invalid_context: 'A context name cannot contain spaces.',
    invalid_namespace: 'Use lowercase letters, digits and dashes (max 63).',
    invalid_kind: 'Choose a resource type.',
    invalid_target: 'Use a Kubernetes name: lowercase letters, digits, “-” and “.”.',
    invalid_remote_port: 'Enter a port between 1 and 65535 or a named port.',
    invalid_port: 'Enter a port between 1 and 65535.',
    invalid_address: 'Enter an IP address or localhost (comma-separate several).',
    port_taken: 'Port is assigned to “{service}”. Each service needs its own local port.',
    port_busy: 'Port is in use on this machine by {owner}.',
    port_denied: 'Ports below 1024 need administrator rights.',
    port_unavailable: 'This address does not exist on this machine.',
    invalid_args: 'These kubectl flags cannot be parsed.',
    args_must_be_flags: 'Extra arguments must be flags, e.g. --pod-running-timeout=1m.',
  };

  function field(error) {
    if (!error) return '';
    const owner = ownerText(error.owner) || t('another program');
    return t(FIELD[error.code] || error.code, { ...error, owner });
  }

  const IMPORT = {
    unbalanced_quotes: 'Unbalanced quotes.',
    unknown_environment: 'Unknown environment “{env}”. Use production, staging, development, testing or legacy.',
    not_port_forward: 'Not a kubectl port-forward command (expected: name = kubectl … port-forward …).',
    missing_flag_value: 'Flag {flag} needs a value.',
    missing_target: 'The resource to forward is missing.',
    unsupported_kind: 'Resource type “{kind}” cannot be forwarded.',
    missing_ports: 'The port mapping is missing.',
    multiple_ports: 'One service forwards one port; split the {count} ports into separate services.',
    invalid_port_spec: 'Invalid port mapping “{spec}”.',
    random_local_port: 'A fixed local port is required (“:{spec}” picks a random one).',
    missing_name: 'A name is required.',
    port_taken: 'Local port is already used by “{service}”.',
    exists: 'A service with this name exists; updating is turned off.',
  };
  const importText = (detail) => t(IMPORT[detail.code] || detail.code, detail);

  function stateLabel(runtime) {
    switch (runtime?.state) {
      case 'healthy':
        return t('Healthy');
      case 'starting':
        return runtime.restarts ? t('Reconnecting') : t('Starting');
      case 'retrying':
        return t('Retrying');
      case 'error':
        return t('Error');
      case 'stopping':
        return t('Stopping');
      default:
        return t('Stopped');
    }
  }

  const TONES = { healthy: 'ok', starting: 'info', retrying: 'warn', error: 'err', stopping: 'idle', stopped: 'idle' };
  const tone = (runtime) => TONES[runtime?.state || 'stopped'];

  window.Messages = { problem, field, importText, stateLabel, tone, ownerText, resourceText };
})();
